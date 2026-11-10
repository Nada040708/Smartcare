"""Bounded read models for the dashboard; no monitoring mutations in HTTP GETs."""
from datetime import datetime, timedelta, timezone
from src.repositories.consent_repository import ConsentRepository


class DashboardQueries:
    def __init__(self, store, patients, runtime=None, *, now=None, max_age_seconds=120):
        self.connection = store.connection
        self.store = store
        self.patients = patients
        self.runtime = runtime or {}
        self.now = now or datetime.now(timezone.utc)
        self.max_age_seconds = max_age_seconds

    def known_ids(self):
        stored = self.connection.execute('SELECT patient_id FROM measurements UNION SELECT patient_id FROM alerts')
        return set(self.patients) | {row['patient_id'] for row in stored}

    def overview(self):
        decisions = {pid:ConsentRepository(self.store).get(pid,self.patients.get(pid)) for pid in self.known_ids()}
        allowed = [pid for pid,decision in decisions.items() if decision['granted']]
        latest = self.connection.execute(
            'SELECT DISTINCT ON (patient_id,parameter) measurement_id,patient_id,parameter,payload FROM measurements '
            'WHERE patient_id=ANY(%s) ORDER BY patient_id,parameter,timestamp DESC,measurement_id DESC',(allowed,)).fetchall()
        for row in latest:
            row['payload'] = self.store.decode_payload('measurements',row['payload'],row['measurement_id'])
        alerts = self.connection.execute("SELECT patient_id,severity,count(*) AS count FROM alerts WHERE status='ACTIVE' AND patient_id=ANY(%s) GROUP BY patient_id,severity",(allowed,)).fetchall()
        counts = {row['patient_id']: row['count'] for row in self.connection.execute('SELECT patient_id,count(*) AS count FROM measurements WHERE patient_id=ANY(%s) GROUP BY patient_id',(allowed,))}
        ids = set(decisions)
        # Device timeouts remain observable during a broker outage.
        live = self.runtime.get('running')
        evaluated = self.runtime.get('evaluated_at')
        live = bool(live and evaluated and (self.now - datetime.fromisoformat(evaluated)).total_seconds() <= 5)
        connections = self.connection.execute('SELECT patient_id,updated_at,payload FROM device_connections WHERE patient_id=ANY(%s)',(allowed,)).fetchall()
        technical = self.connection.execute("SELECT patient_id,payload FROM technical_events WHERE status='ACTIVE' AND type IN ('DISCONNECTED','MISSING_DATA') AND patient_id=ANY(%s) ORDER BY timestamp DESC",(allowed,)).fetchall()
        result = []
        for pid in sorted(ids):
            patient = self.patients.get(pid)
            readings = {r['parameter']: dict(r['payload'], stale=(self.now-datetime.fromisoformat(r['payload']['timestamp'])).total_seconds() > self.max_age_seconds) for r in latest if r['patient_id'] == pid}
            if live:
                for row in connections:
                    if row['patient_id'] != pid or (self.now-row['updated_at']).total_seconds()>5:
                        continue
                    for parameter in row['payload']['missing_parameters']:
                        reading = readings.get(parameter)
                        if reading and reading['device_id'] == row['payload']['device_id']:
                            reading['stale'] = True
            active = {r['severity']: r['count'] for r in alerts if r['patient_id'] == pid}
            state = 'CRITICAL' if active.get('CRITICAL') else 'ALERT' if active.get('WARNING') else 'SURVEILLANCE'
            if live and patient and patient.monitoring_enabled and decisions[pid]['granted']:
                current = self.runtime.get('states', {}).get(pid)
                if current in {'NORMAL', 'SURVEILLANCE', 'ALERT', 'CRITICAL', 'DISCONNECTED'}:
                    state = current
                # A database commit can precede publication of the receiver snapshot.
                if state != 'DISCONNECTED':
                    if active.get('CRITICAL'):
                        state = 'CRITICAL'
                    elif active.get('WARNING'):
                        state = 'ALERT'
                    elif active.get('INFO') or not readings or any(r['stale'] for r in readings.values()) or not self.runtime.get('connected'):
                        state = 'SURVEILLANCE'
            result.append(dict(patient_id=pid, name=patient.name if patient else pid, configured=bool(patient),
                               profiles=[{'id': p.profile_id, 'name': p.name} for p in patient.profiles] if patient else [],
                               priority_parameters=patient.get_priority_parameters() if patient else [],
                               monitoring_enabled=bool(patient and patient.monitoring_enabled and decisions[pid]['granted']),
                               consent=decisions[pid],
                               state=state, latest=readings, last_measurement_at=max((r['timestamp'] for r in readings.values()), default=None),
                               active_alerts=sum(active.values()), measurement_count=counts.get(pid, 0),
                               devices=[dict(device_id=row['payload']['device_id'],
                                   status=row['payload']['status'] if live and (self.now-row['updated_at']).total_seconds()<=5 else 'UNKNOWN',
                                   last_status=row['payload']['status'], last_seen_at=row['payload']['last_seen_at'],
                                   missing_parameters=row['payload']['missing_parameters'], updated_at=row['updated_at'].isoformat())
                                   for row in connections if row['patient_id']==pid],
                               technical_alerts=[row['payload'] for row in technical if row['patient_id']==pid]))
        visible_runtime = dict(self.runtime, states={pid:state for pid,state in self.runtime.get('states',{}).items() if pid in allowed})
        return dict(patients=result, generated_at=self.now.isoformat(), runtime=visible_runtime,
                    totals=dict(patients=len(result), active_alerts=sum(r['count'] for r in alerts),
                                critical_patients=sum(p['state'] == 'CRITICAL' for p in result),
                                measurements=sum(counts.values())))

    def history(self, patient_id, parameter, minutes, limit):
        rows = self.connection.execute(
            'SELECT measurement_id,payload FROM measurements WHERE patient_id=%s AND parameter=%s AND timestamp >= %s '
            'ORDER BY timestamp DESC,measurement_id DESC LIMIT %s',
            (patient_id, parameter, self.now-timedelta(minutes=minutes), limit+1)).fetchall()
        return dict(items=[self.store.decode_payload('measurements',r['payload'],r['measurement_id']) for r in reversed(rows[:limit])], truncated=len(rows) > limit,
                    parameter=parameter, minutes=minutes, limit=limit)

    def alerts(self, patient_id, status, severity, limit, offset):
        condition = '(%s::text IS NULL OR patient_id=%s) AND (%s=%s OR status=%s) AND (%s=%s OR severity=%s)'
        params = (patient_id, patient_id, status, 'ALL', status, severity, 'ALL', severity)
        allowed = [pid for pid in self.known_ids() if ConsentRepository(self.store).get(pid,self.patients.get(pid))['granted']]
        condition += ' AND patient_id=ANY(%s)'
        params += (allowed,)
        total = self.connection.execute('SELECT count(*) AS count FROM alerts WHERE ' + condition, params).fetchone()['count']
        rows = list(self.connection.execute('SELECT alert_id,payload FROM alerts WHERE ' + condition + ' ORDER BY timestamp DESC,alert_id DESC LIMIT %s OFFSET %s', params+(limit, offset)))
        items = [self.store.decode_payload('alerts',r['payload'],r['alert_id']) for r in rows]
        identifiers = [row['alert_id'] for row in rows]
        actions = self.connection.execute('''SELECT aa.alert_id,aa.action,aa.timestamp,
            actor.username AS actor,target.username AS target
            FROM alert_actions aa JOIN users actor ON actor.user_id=aa.actor_id
            LEFT JOIN users target ON target.user_id=aa.target_user_id
            WHERE aa.alert_id=ANY(%s) ORDER BY aa.timestamp''', (identifiers,)).fetchall() if identifiers else []
        for item in items:
            item['actions'] = [dict(action=row['action'], timestamp=row['timestamp'].isoformat(),
                                    actor=row['actor'], target=row['target'])
                               for row in actions if row['alert_id'] == item['alert_id']]
        return dict(items=items, total=total, limit=limit, offset=offset)

    def events(self, patient_id, limit):
        return [r['payload'] for r in self.connection.execute(
            'SELECT payload FROM technical_events WHERE patient_id=%s ORDER BY timestamp DESC,event_id DESC LIMIT %s', (patient_id, limit))]
