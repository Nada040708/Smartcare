"""Explicit JSON records: historical reads never apply live-data age limits."""
from dataclasses import asdict
from datetime import datetime, timezone
import json

from src.domain import Alert, Measurement
from src.domain.technical_event import TechnicalEvent


def timestamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('Storage requires timezone-aware timestamps')
    return value.astimezone(timezone.utc).isoformat()


def nonempty(*values):
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError('Storage identifiers and messages must be non-empty strings')


def measurement_record(measurement):
    if measurement.parameter is None or measurement.quality not in {'valid', 'good'}:
        raise ValueError('Only accepted scalar measurements can be stored')
    data = measurement.to_dict()
    data['timestamp'] = timestamp(measurement.timestamp)
    data['ieee11073_metadata']['timestamp'] = data['timestamp']
    return data


def measurement_from_record(data):
    return Measurement(data['measurement_id'], data['patient_id'],
                       timestamp=datetime.fromisoformat(data['timestamp']),
                       device_id=data['device_id'], reading_id=data['reading_id'],
                       parameter=data['parameter'], value=data['value'], unit=data['unit'],
                       quality=data['quality'], device_type=data['ieee11073_metadata']['device_type'])


def alert_record(alert):
    nonempty(alert.alert_id, alert.patient_id, alert.rule_id, alert.message)
    if alert.severity not in {'INFO', 'WARNING', 'CRITICAL'} or alert.status not in {'ACTIVE', 'RESOLVED'}:
        raise ValueError('Invalid alert severity or status')
    for name, minimum in [('occurrences', 1), ('recovery_count', 0)]:
        value = getattr(alert, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f'Invalid {name}')
    for ids in (alert.profile_ids, alert.measurement_ids, alert.recovery_measurement_ids):
        if not isinstance(ids, list):
            raise ValueError('Alert provenance must contain lists')
        nonempty(*ids)
    data = {name: getattr(alert, name) for name in (
        'alert_id', 'patient_id', 'rule_id', 'parameter', 'severity', 'message', 'status',
        'profile_ids', 'measurement_ids', 'occurrences', 'recovery_count',
        'recovery_measurement_ids', 'resolution_reason',
    )}
    data.update(timestamp=timestamp(alert.timestamp), last_seen_at=timestamp(alert.last_seen_at),
                resolved_at=timestamp(alert.resolved_at) if alert.resolved_at is not None else None)
    if alert.last_seen_at < alert.timestamp:
        raise ValueError('Last occurrence precedes opening')
    if alert.status == 'ACTIVE' and (alert.resolved_at is not None or alert.resolution_reason is not None):
        raise ValueError('Active alert cannot have resolution metadata')
    if alert.status == 'RESOLVED':
        nonempty(alert.resolution_reason)
        if alert.resolved_at is None or alert.resolved_at < alert.last_seen_at:
            raise ValueError('Invalid resolution timestamp')
    return json.loads(json.dumps(data, allow_nan=False))


def alert_from_record(data):
    alert = Alert(data['alert_id'], data['patient_id'], data['severity'], data['message'],
                  timestamp=datetime.fromisoformat(data['timestamp']), status=data['status'],
                  rule_id=data['rule_id'], parameter=data['parameter'],
                  profile_ids=data['profile_ids'], measurement_ids=data['measurement_ids'])
    for name in ('occurrences', 'recovery_count', 'recovery_measurement_ids', 'resolution_reason'):
        setattr(alert, name, data[name])
    alert.last_seen_at = datetime.fromisoformat(data['last_seen_at'])
    alert.resolved_at = datetime.fromisoformat(data['resolved_at']) if data['resolved_at'] else None
    return alert


def event_record(event):
    nonempty(event.event_id, event.type, event.description)
    if event.status not in {'RECORDED', 'ACTIVE', 'RESOLVED'} or not isinstance(event.details, dict):
        raise ValueError('Invalid technical event')
    for value in (event.patient_id, event.device_id):
        if value is not None:
            nonempty(value)
    data = asdict(event)
    data['timestamp'] = timestamp(event.timestamp)
    return json.loads(json.dumps(data, allow_nan=False))


def event_from_record(data):
    return TechnicalEvent(**dict(data, timestamp=datetime.fromisoformat(data['timestamp'])))
