"""Atomic persistence around the existing sequential monitoring pipeline."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import json

from src.domain import TechnicalEvent
from src.domain import MonitoringState
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
from src.repositories.postgres_repositories import (PostgresMeasurementRepository,
                                                    PostgresAlertRepository, PostgresEventRepository)
from .anomaly_detector import AnomalyDetector
from .alert_engine import AlertEngine
from .monitoring_state_manager import MonitoringStateManager
from src.repositories.storage_codecs import measurement_from_record
from src.repositories.consent_repository import ConsentRepository, ConsentRequired


class PersistentMonitoring:
    def __init__(self, store, *, detector=None, restarted_at=None, connection_monitor=None,
                 auto_resolve_alerts=True):
        if store.connection.info.transaction_status != TransactionStatus.IDLE:
            raise RuntimeError('Create the session outside a database transaction')
        self.store = store
        store.acquire_writer()
        self.measurements = PostgresMeasurementRepository(store)
        self.alerts = PostgresAlertRepository(store)
        self.events = PostgresEventRepository(store)
        self.detector = detector or AnomalyDetector()
        self.engine = AlertEngine(auto_resolve=auto_resolve_alerts)
        self.states = MonitoringStateManager()
        self.connections = connection_monitor
        restarted_at = restarted_at or datetime.now(timezone.utc)
        with store.transaction():
            if self.connections:
                self.connections.restore([row['payload'] for row in store.connection.execute('SELECT payload FROM device_connections')])
            restored = self.engine.restore_active(self.alerts.getActive(), restarted_at=restarted_at)
            for alert in restored:
                self.alerts.save(alert)
            for patient_id in {alert.patient_id for alert in restored}:
                severities = {a.severity for a in restored if a.patient_id == patient_id}
                self.states.current_states[patient_id] = (
                    MonitoringState.CRITICAL if 'CRITICAL' in severities else
                    MonitoringState.ALERT if 'WARNING' in severities else MonitoringState.SURVEILLANCE
                )
            self.events.save(TechnicalEvent(
                str(uuid4()), 'MONITORING_STARTED', 'Session de surveillance démarrée',
                timestamp=restarted_at, details={'restored_active_alerts': len(restored)},
            ))

    def process(self, measurements, patient, *, connected=True):
        if self.store.connection.info.transaction_status != TransactionStatus.IDLE:
            raise RuntimeError('process() owns its transaction; do not wrap it in another transaction')
        # Restore runtime state as well as SQL rows if validation or saving fails.
        components = (self.detector, self.engine, self.states) + ((self.connections,) if self.connections else ())
        snapshots = [deepcopy(component.__dict__) for component in components]
        try:
            with self.store.transaction():
                consent = ConsentRepository(self.store)
                consent.lock(patient.patient_id)
                if not consent.get(patient.patient_id,patient)['granted']:
                    if measurements:
                        raise ConsentRequired('Patient consent is required before collecting measurements')
                    patient = deepcopy(patient)
                    patient.monitoring_enabled = False
                fresh = []
                for measurement in measurements:
                    if measurement.patient_id != patient.patient_id:
                        raise ValueError('Measurement/patient mismatch')
                    if self.measurements.save(measurement):
                        if not self.detector.validator.validate(measurement):
                            raise ValueError('Invalid or stale measurement; transaction cancelled')
                        fresh.append(measurement)
                complete = True
                if self.connections:
                    device_connected, complete, events = self.connections.evaluate(patient, fresh, now=self.detector.validator.now())
                    connected = connected and device_connected
                    if any(event.status == 'ACTIVE' and event.type in {'DISCONNECTED', 'MISSING_DATA'} for event in events):
                        # A trend must not bridge a gap in the acquisition chain.
                        self.detector.clear_patient(patient.patient_id)
                    for event in events:
                        self.events.save(event)
                    for snapshot in self.connections.snapshots(patient.patient_id):
                        self.store.connection.execute('''INSERT INTO device_connections VALUES (%s,%s,%s,%s)
                            ON CONFLICT (patient_id,device_id) DO UPDATE SET updated_at=EXCLUDED.updated_at,payload=EXCLUDED.payload''',
                            (patient.patient_id, snapshot['device_id'], self.detector.validator.now(), Jsonb(snapshot)))
                report = self.detector.evaluate_batch(fresh, patient)
                for alert in self.engine.process(report, connected=connected, recovery_allowed=complete):
                    self.alerts.save(alert)
                before = self.states.get_state(patient.patient_id)
                after = self.states.evaluate_state(report, self.engine.get_active(), connected=connected, complete=complete)
                if before != after:
                    self.events.save(TechnicalEvent(
                        str(uuid4()), 'STATE_CHANGED', f'{before.value} → {after.value}',
                        patient_id=patient.patient_id, timestamp=report.timestamp,
                        details={'previous_state': before.value, 'state': after.value},
                    ))
            return report, after
        except BaseException:
            for component, snapshot in zip(components, snapshots):
                component.__dict__.clear()
                component.__dict__.update(snapshot)
            raise

    def process_payload(self, payload, patient, *, topic=None):
        validation = self.detector.validator.validate_payload(payload, topic=topic)
        if not validation.accepted:
            raise ValueError(f'Invalid received measurement: {validation.to_dict()}')
        data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
        return self.process([measurement_from_record(data)], patient)

    def resolve_alert(self, alert_id, actor_id):
        """Close one live episode explicitly and record who performed the action."""
        from src.domain import MonitoringState
        from src.security.authentication import AuditLog
        target = next((alert for alert in self.engine.get_active() if alert.alert_id == alert_id), None)
        if target is None:
            return None
        with self.store.transaction():
            resolved = self.engine.resolve_alert(target.patient_id, target.rule_id,
                                                 datetime.now(timezone.utc), 'MANUAL_CLINICIAN')
            self.alerts.save(resolved)
            self.store.connection.execute('''INSERT INTO alert_actions
                (action_id,alert_id,actor_id,action) VALUES (%s,%s,%s,'RESOLVED')''',
                (uuid4(), alert_id, actor_id))
            AuditLog.record(self.store.connection, 'ALERT_RESOLVED', actor_id, alert_id)
            remaining = self.engine.get_active(target.patient_id)
            severities = {alert.severity for alert in remaining}
            self.states.current_states[target.patient_id] = (
                MonitoringState.CRITICAL if 'CRITICAL' in severities else
                MonitoringState.ALERT if 'WARNING' in severities else
                MonitoringState.SURVEILLANCE
            )
        return resolved
