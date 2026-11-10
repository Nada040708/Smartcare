"""SQL implementations of the UML repositories, sharing a PostgresStore."""
from psycopg import sql
from psycopg.types.json import Jsonb

from .storage_codecs import (measurement_record, measurement_from_record, alert_record,
                             alert_from_record, event_record, event_from_record)


class _Repository:
    def __init__(self, store):
        self.store = store

    def _history(self, patient_id=None, *, limit=None, offset=0, active=False):
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
            raise ValueError('limit must be a positive integer')
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError('offset must be a non-negative integer')
        query = sql.SQL('SELECT {},payload FROM {} WHERE (%s::text IS NULL OR patient_id = %s)').format(sql.Identifier(self.id_column),sql.Identifier(self.table))
        if active:
            query += sql.SQL(" AND status = 'ACTIVE'")
        query += sql.SQL(' ORDER BY timestamp, {} LIMIT %s OFFSET %s').format(sql.Identifier(self.id_column))
        rows = self.store.connection.execute(query, (patient_id, patient_id, limit, offset))
        return [self.decode(self.store.decode_payload(self.table,row['payload'],row[self.id_column])
                           if self.table in {'measurements','alerts'} else row['payload']) for row in rows]

    def count(self, patient_id=None, *, active=False):
        query = sql.SQL('SELECT count(*) AS count FROM {} WHERE (%s::text IS NULL OR patient_id = %s)').format(sql.Identifier(self.table))
        if active:
            query += sql.SQL(" AND status = 'ACTIVE'")
        return self.store.connection.execute(query, (patient_id, patient_id)).fetchone()['count']

    def getHistory(self, patient_id=None, *, limit=None, offset=0):
        return self._history(patient_id, limit=limit, offset=offset)

    def getByPatient(self, patient_id, *, limit=None, offset=0):
        return self.getHistory(patient_id, limit=limit, offset=offset)


class PostgresMeasurementRepository(_Repository):
    table = 'measurements'
    id_column = 'measurement_id'
    decode = staticmethod(measurement_from_record)

    def get_payload(self, measurement_id):
        row = self.store.connection.execute(
            'SELECT m.measurement_id,m.payload FROM measurement_receipts r JOIN measurements m USING (measurement_id) WHERE r.message_id = %s',
            (measurement_id,),
        ).fetchone()
        return self.store.decode_payload(self.table,row['payload'],row['measurement_id']) if row else None

    @staticmethod
    def _same_reading(stored, incoming):
        if dict(stored, measurement_id=incoming['measurement_id']) != incoming:
            raise ValueError('Measurement or reading identifier reused with different data')

    def save(self, measurement):
        """Return True only for a new reading; replays are durably idempotent."""
        data = measurement_record(measurement)
        connection = self.store.connection
        with self.store.transaction():
            existing = self.get_payload(data['measurement_id'])
            if existing is not None:
                self._same_reading(existing, data)
                return False
            inserted = connection.execute(
                'INSERT INTO measurements (measurement_id, patient_id, device_id, reading_id, parameter, unit, quality, timestamp, payload) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING measurement_id',
                tuple(data[k] for k in ('measurement_id', 'patient_id', 'device_id', 'reading_id', 'parameter', 'unit', 'quality', 'timestamp')) + (Jsonb(self.store.encode_payload(self.table,data)),),
            ).fetchone()
            canonical_id = data['measurement_id']
            if not inserted:
                row = connection.execute(
                    'SELECT measurement_id,payload FROM measurements WHERE measurement_id = %s OR '
                    '(patient_id = %s AND device_id = %s AND parameter = %s AND reading_id = %s)',
                    tuple(data[k] for k in ('measurement_id', 'patient_id', 'device_id', 'parameter', 'reading_id')),
                ).fetchone()
                self._same_reading(self.store.decode_payload(self.table,row['payload'],row['measurement_id']), data)
                canonical_id = row['measurement_id']
            connection.execute('INSERT INTO measurement_receipts VALUES (%s,%s) ON CONFLICT DO NOTHING',
                               (data['measurement_id'], canonical_id))
            # Also check an alias inserted concurrently by another repository client.
            self._same_reading(self.get_payload(data['measurement_id']), data)
            return bool(inserted)


class PostgresAlertRepository(_Repository):
    table = 'alerts'
    id_column = 'alert_id'
    decode = staticmethod(alert_from_record)

    def getActive(self, patient_id=None):
        return self._history(patient_id, active=True)

    def save(self, alert):
        data = alert_record(alert)
        connection = self.store.connection
        with self.store.transaction():
            row = connection.execute('SELECT payload FROM alerts WHERE alert_id = %s FOR UPDATE', (alert.alert_id,)).fetchone()
            if row:
                previous = self.store.decode_payload(self.table,row['payload'],alert.alert_id)
                if previous == data:
                    return False
                if any(previous[k] != data[k] for k in ('patient_id', 'rule_id', 'timestamp')):
                    raise ValueError('Cannot change the identity of an alert episode')
                if previous['status'] == 'RESOLVED':
                    raise ValueError('A resolved episode is immutable; create a new episode')
                if data['occurrences'] < previous['occurrences'] or data['last_seen_at'] < previous['last_seen_at']:
                    raise ValueError('Cannot overwrite an alert with an older version')
                connection.execute(
                    'UPDATE alerts SET severity=%s, status=%s, last_seen_at=%s, resolved_at=%s, occurrences=%s, payload=%s WHERE alert_id=%s',
                    tuple(data[k] for k in ('severity', 'status', 'last_seen_at', 'resolved_at', 'occurrences')) + (Jsonb(self.store.encode_payload(self.table,data)), alert.alert_id),
                )
            else:
                connection.execute(
                    'INSERT INTO alerts (alert_id,patient_id,rule_id,severity,status,timestamp,last_seen_at,resolved_at,occurrences,payload) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    tuple(data[k] for k in ('alert_id', 'patient_id', 'rule_id', 'severity', 'status', 'timestamp', 'last_seen_at', 'resolved_at', 'occurrences')) + (Jsonb(self.store.encode_payload(self.table,data)),),
                )
            return True


class PostgresEventRepository(_Repository):
    table = 'technical_events'
    id_column = 'event_id'
    decode = staticmethod(event_from_record)

    def save(self, event):
        data = event_record(event)
        with self.store.transaction():
            row = self.store.connection.execute('SELECT payload FROM technical_events WHERE event_id=%s FOR UPDATE', (event.event_id,)).fetchone()
            if row:
                previous = row['payload']
                if previous == data:
                    return False
                if any(previous[k] != data[k] for k in ('patient_id', 'device_id', 'type', 'timestamp')):
                    raise ValueError('Cannot change event identity')
                if previous['status'] in {'RESOLVED', 'RECORDED'}:
                    raise ValueError('A completed event is immutable')
                self.store.connection.execute('UPDATE technical_events SET status=%s,payload=%s WHERE event_id=%s',
                                               (event.status, Jsonb(data), event.event_id))
            else:
                self.store.connection.execute(
                    'INSERT INTO technical_events (event_id,patient_id,device_id,type,status,timestamp,payload) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    tuple(data[k] for k in ('event_id', 'patient_id', 'device_id', 'type', 'status', 'timestamp')) + (Jsonb(data),),
                )
        return True
