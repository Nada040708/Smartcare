from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from psycopg.errors import UniqueViolation

from src.domain import Alert, Measurement, Patient, TechnicalEvent, ThresholdRule
from src.domain.consent import Consent
from src.processing import AnomalyDetector, DataValidator
from src.processing.persistent_monitoring import PersistentMonitoring
from src.repositories.postgres_store import PostgresStore
from src.repositories.postgres_repositories import (PostgresMeasurementRepository,
                                                    PostgresAlertRepository, PostgresEventRepository)

pytestmark = pytest.mark.postgres_integration


def measurement(value=80, *, patient_id='P001', timestamp=None, measurement_id=None):
    return Measurement(measurement_id or str(uuid4()), patient_id, parameter='heart_rate',
                       value=value, unit='bpm', device_id='SIM', quality='valid',
                       timestamp=timestamp or datetime.now(timezone.utc), device_type='simulator')


def detector(clock):
    rule = ThresholdRule(rule_id='hr', parameter='heart_rate', operator='>', threshold=100,
                         severity='WARNING', message='Seuil de démonstration')
    return AnomalyDetector(DataValidator(now=lambda: clock[0]), common_rules=[rule])


def test_measurements_survive_reopen_keep_metadata_and_detach_objects(postgres_schema):
    historical = measurement(timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc))
    payload = historical.to_dict()
    with PostgresStore(schema=postgres_schema) as store:
        repository = PostgresMeasurementRepository(store)
        assert repository.save(historical)
        historical.value = 170
    with PostgresStore(schema=postgres_schema) as reopened:
        repository = PostgresMeasurementRepository(reopened)
        assert repository.get_payload(payload['measurement_id']) == payload
        rows = repository.getByPatient('P001')
        assert rows[0].to_dict() == payload
        rows[0].value = 180
        assert repository.getHistory()[0].value == 80
        assert repository.getByPatient('P002') == []
        assert [r['version'] for r in reopened.connection.execute('SELECT version FROM schema_migrations ORDER BY version')] == [1, 2, 3, 4, 5]


def test_duplicate_messages_and_reading_aliases_survive_reopen(postgres_schema):
    reading = measurement()
    alias = deepcopy(reading)
    alias.measurement_id = str(uuid4())
    with PostgresStore(schema=postgres_schema) as store:
        repo = PostgresMeasurementRepository(store)
        assert repo.save(reading)
        assert not repo.save(reading)
        assert not repo.save(alias)
    with PostgresStore(schema=postgres_schema) as store:
        repo = PostgresMeasurementRepository(store)
        assert not repo.save(alias)
        assert repo.count() == 1
        alias.value = 140
        with pytest.raises(ValueError, match='reused'):
            repo.save(alias)
        assert repo.count() == 1


def test_patient_filtering_order_pagination_and_sql_parameters(postgres_schema):
    malicious_id = "P'; DROP TABLE measurements; --"
    now = datetime.now(timezone.utc)
    with PostgresStore(schema=postgres_schema) as store:
        repo = PostgresMeasurementRepository(store)
        for index in (2, 0, 1):
            repo.save(measurement(80+index, timestamp=now+timedelta(seconds=index)))
        repo.save(measurement(patient_id=malicious_id))
        assert [m.value for m in repo.getByPatient('P001', limit=1, offset=1)] == [81]
        assert repo.count('P001') == 3 and repo.count(malicious_id) == 1
        assert len(repo.getByPatient(malicious_id)) == 1
        with pytest.raises(ValueError):
            repo.getHistory(limit=0)
        with pytest.raises(ValueError):
            repo.getHistory(offset=-1)


def test_alert_updates_resolution_provenance_and_unique_active_rule(postgres_schema):
    now = datetime.now(timezone.utc)
    alert = Alert('A1', 'P001', 'WARNING', 'Démo', timestamp=now, rule_id='hr',
                  parameter='heart_rate', profile_ids=['common'], measurement_ids=['M1'])
    with PostgresStore(schema=postgres_schema) as store:
        repo = PostgresAlertRepository(store)
        repo.save(alert)
        repo.save(alert)
        duplicate = deepcopy(alert)
        duplicate.alert_id = 'A2'
        with pytest.raises(UniqueViolation):
            repo.save(duplicate)
        alert.occurrences = 2
        alert.last_seen_at = now + timedelta(seconds=1)
        alert.recovery_count = 1
        alert.recovery_measurement_ids = ['M2']
        repo.save(alert)
    with PostgresStore(schema=postgres_schema) as store:
        repo = PostgresAlertRepository(store)
        restored = repo.getActive()[0]
        assert restored.occurrences == 2 and restored.recovery_count == 1
        assert restored.profile_ids == ['common'] and restored.recovery_measurement_ids == ['M2']
        restored.resolve(now + timedelta(seconds=3), 'RECOVERY_CONFIRMED')
        repo.save(restored)
        with pytest.raises(ValueError, match='immutable'):
            repo.save(alert)  # A stale active object cannot reopen the resolved row.
        duplicate.timestamp = now + timedelta(seconds=4)
        duplicate.last_seen_at = duplicate.timestamp
        repo.save(duplicate)
        assert repo.count() == 2 and repo.count(active=True) == 1


def test_event_storage_resolution_and_completed_event_immutability(postgres_schema):
    event = TechnicalEvent('E1', 'DISCONNECTED', 'Panne simulée', 'P001', 'SIM', status='ACTIVE')
    with PostgresStore(schema=postgres_schema) as store:
        events = PostgresEventRepository(store)
        events.save(event)
        event.status = 'RESOLVED'
        event.details = {'reason': 'recovery'}
        events.save(event)
    with PostgresStore(schema=postgres_schema) as store:
        events = PostgresEventRepository(store)
        assert events.getHistory()[0] == event
        assert events.count('P002') == 0
        event.status = 'ACTIVE'
        with pytest.raises(ValueError, match='immutable'):
            events.save(event)


def test_transaction_rolls_back_all_repositories(postgres_schema):
    with PostgresStore(schema=postgres_schema) as store:
        measurements = PostgresMeasurementRepository(store)
        alerts = PostgresAlertRepository(store)
        events = PostgresEventRepository(store)
        with pytest.raises(RuntimeError):
            with store.transaction():
                measurements.save(measurement())
                alerts.save(Alert('A', 'P001', 'WARNING', 'Démo', rule_id='hr'))
                events.save(TechnicalEvent('E', 'TEST', 'Test transactionnel'))
                raise RuntimeError('simulated failure')
        assert measurements.count() == alerts.count() == events.count() == 0


def test_session_restart_reuses_active_episode_rejects_replay_and_resets_recovery(postgres_schema):
    clock = [datetime.now(timezone.utc)]
    patient = Patient('P001', 'Patient fictif',consent=Consent('P001',True))
    bad = measurement(140, timestamp=clock[0])
    with PostgresStore(schema=postgres_schema) as store:
        session = PersistentMonitoring(store, detector=detector(clock), restarted_at=clock[0])
        session.process([bad], patient)
        alert_id = session.alerts.getActive()[0].alert_id
        clock[0] += timedelta(seconds=1)
        normal = measurement(80, timestamp=clock[0])
        session.process([normal], patient)
        assert session.alerts.getActive()[0].recovery_count == 1
    clock[0] += timedelta(seconds=1)
    with PostgresStore(schema=postgres_schema) as store:
        session = PersistentMonitoring(store, detector=detector(clock), restarted_at=clock[0])
        assert session.alerts.getActive()[0].recovery_count == 0
        report, state = session.process([bad, normal], patient)
        assert not report.anomalies and state.value == 'ALERT'
        assert session.measurements.count() == 2
        assert session.alerts.getActive()[0].occurrences == 1
        for index in range(2):
            clock[0] += timedelta(seconds=1)
            _, state = session.process([measurement(81, timestamp=clock[0])], patient)
            assert state.value == ('ALERT' if index == 0 else 'NORMAL')
        assert session.alerts.getHistory()[0].alert_id == alert_id
        assert session.alerts.getHistory()[0].status == 'RESOLVED'
        clock[0] += timedelta(seconds=1)
        session.process([measurement(145, timestamp=clock[0])], patient)
        assert session.alerts.count() == 2
        assert session.alerts.getActive()[0].alert_id != alert_id
        assert any(e.type == 'STATE_CHANGED' for e in session.events.getByPatient('P001'))


def test_session_rolls_back_detector_and_engine_after_storage_failure(postgres_schema, monkeypatch):
    clock = [datetime.now(timezone.utc)]
    patient = Patient('P001', 'Patient fictif',consent=Consent('P001',True))
    reading = measurement(140, timestamp=clock[0])
    with PostgresStore(schema=postgres_schema) as store:
        session = PersistentMonitoring(store, detector=detector(clock), restarted_at=clock[0])
        original = session.events.save
        def fail(event):
            raise RuntimeError('injected event write failure')
        monkeypatch.setattr(session.events, 'save', fail)
        with pytest.raises(RuntimeError, match='injected'):
            session.process([reading], patient)
        assert session.measurements.count() == session.alerts.count() == 0
        assert not session.engine.get_active()
        monkeypatch.setattr(session.events, 'save', original)
        _, state = session.process([reading], patient)
        assert state.value == 'ALERT' and session.alerts.count() == 1


def test_invalid_or_cross_patient_cycle_leaves_no_partial_records(postgres_schema):
    clock = [datetime.now(timezone.utc)]
    with PostgresStore(schema=postgres_schema) as store:
        session = PersistentMonitoring(store, detector=detector(clock))
        valid = measurement(140, timestamp=clock[0])
        invalid = measurement(1000, timestamp=clock[0])
        for readings in ([valid, invalid], [valid, measurement(patient_id='P002')]):
            with pytest.raises(ValueError):
                session.process(readings, Patient('P001', 'Patient fictif',consent=Consent('P001',True)))
            assert session.measurements.count() == session.alerts.count() == 0


def test_schema_has_only_one_monitoring_writer_and_releases_it_on_close(postgres_schema):
    with PostgresStore(schema=postgres_schema) as first:
        PersistentMonitoring(first)
        with PostgresStore(schema=postgres_schema) as second:
            with pytest.raises(RuntimeError, match='already'):
                PersistentMonitoring(second)
    with PostgresStore(schema=postgres_schema) as reopened:
        PersistentMonitoring(reopened)


def test_recovery_cannot_use_newly_received_but_pre_restart_samples(postgres_schema):
    clock = [datetime.now(timezone.utc)]
    with PostgresStore(schema=postgres_schema) as store:
        session = PersistentMonitoring(store, detector=detector(clock))
        session.process([measurement(140, timestamp=clock[0])], Patient('P001', 'P1',consent=Consent('P001',True)))
    restart = clock[0] + timedelta(seconds=10)
    clock[0] = restart
    with PostgresStore(schema=postgres_schema) as store:
        session = PersistentMonitoring(store, detector=detector(clock), restarted_at=restart)
        for age in (3, 2, 1):
            session.process([measurement(80, timestamp=restart-timedelta(seconds=age))], Patient('P001', 'P1',consent=Consent('P001',True)))
        assert session.alerts.getActive()[0].recovery_count == 0


def test_main_default_persists_across_invocations(postgres_schema, capsys):
    import main
    args = ['--no-mqtt', '--cycles', '1', '--db-schema', postgres_schema]
    main.main(args)
    main.main(args)
    output = capsys.readouterr().out
    assert "'measurements_count': 7" in output and "'measurements_count': 14" in output


def test_future_schema_version_is_refused(postgres_schema):
    with PostgresStore(schema=postgres_schema) as store:
        store.connection.execute('INSERT INTO schema_migrations VALUES (99)')
        try:
            with pytest.raises(ValueError, match='version'):
                PostgresStore(schema=postgres_schema)
        finally:
            store.connection.execute('DELETE FROM schema_migrations WHERE version=99')
