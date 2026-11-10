from datetime import datetime, timedelta, timezone

import pytest

from src.domain import Alert, Measurement, TechnicalEvent
from src.repositories.storage_codecs import (measurement_record, measurement_from_record,
                                             alert_record, alert_from_record, event_record, event_from_record)
from src.repositories.postgres_store import PostgresStore


def scalar():
    return Measurement('M', 'P', parameter='spo2', value=98, unit='%', device_id='SIM', quality='valid')


def test_storage_normalizes_utc_and_preserves_measurement_metadata():
    measure = scalar()
    measure.timestamp = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=1)))
    data = measurement_record(measure)
    assert data['timestamp'] == '2026-01-01T11:00:00+00:00'
    assert data['ieee11073_metadata']['timestamp'] == data['timestamp']
    assert measurement_from_record(data).to_dict() == data


@pytest.mark.parametrize('quality', ['invalid', 'questionable'])
def test_storage_refuses_unaccepted_quality(quality):
    measure = scalar()
    measure.quality = quality
    with pytest.raises(ValueError):
        measurement_record(measure)


def test_storage_refuses_legacy_batches_and_naive_dates():
    with pytest.raises(ValueError):
        measurement_record(Measurement('M', 'P', values={'heart_rate': 80}))
    measure = scalar()
    measure.timestamp = datetime(2026, 1, 1)
    with pytest.raises(ValueError):
        measurement_record(measure)


def test_alert_record_is_a_detached_snapshot_with_complete_resolution():
    alert = Alert('A', 'P', 'WARNING', 'Démo', rule_id='hr', measurement_ids=['M'])
    alert.recovery_count = 2
    alert.recovery_measurement_ids = ['R']
    alert.resolve(reason='RECOVERY_CONFIRMED')
    data = alert_record(alert)
    alert.measurement_ids.append('another')
    restored = alert_from_record(data)
    assert restored.measurement_ids == ['M']
    assert restored.status == 'RESOLVED' and restored.recovery_count == 2
    assert restored.resolution_reason == 'RECOVERY_CONFIRMED'


@pytest.mark.parametrize('field,value', [('severity','BAD'), ('status','BAD'), ('rule_id',None),
                                        ('occurrences',0), ('recovery_count',True)])
def test_invalid_alert_cannot_be_serialized(field, value):
    alert = Alert('A', 'P', 'WARNING', 'Démo', rule_id='hr')
    setattr(alert, field, value)
    with pytest.raises(ValueError):
        alert_record(alert)


def test_event_record_preserves_details_and_rejects_non_json_values():
    event = TechnicalEvent('E', 'STATE_CHANGED', 'État modifié', details={'state':'ALERT'})
    assert event_from_record(event_record(event)) == event
    event.details = {'invalid': float('nan')}
    with pytest.raises(ValueError):
        event_record(event)


@pytest.mark.parametrize('schema', ['public;DROP TABLE x', '', 'UPPERCASE', '../x'])
def test_schema_identifiers_are_checked_before_any_connection(schema):
    with pytest.raises(ValueError, match='schema'):
        PostgresStore(schema=schema)
