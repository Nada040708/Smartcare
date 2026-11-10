"""Per-device silence and per-parameter freshness; no clinical diagnosis."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from uuid import uuid4

from src.domain import TechnicalEvent
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.repositories.storage_codecs import event_record, event_from_record

DEFAULT_POLICY = Path(__file__).resolve().parents[2]/'config/connection-policy.json'


def load_connection_policy(path=DEFAULT_POLICY):
    policy = json.loads(Path(path).read_text())
    if not isinstance(policy, dict) or set(policy) != {'timeout_seconds', 'startup_grace_seconds', 'devices'}:
        raise ValueError('Invalid connection policy')
    for key in ('timeout_seconds', 'startup_grace_seconds'):
        value = policy[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 3600:
            raise ValueError('Connection deadlines must be between 1 and 3600 seconds')
    if not isinstance(policy['devices'], list):
        raise ValueError('devices must be a list')
    seen = set()
    for device in policy['devices']:
        if not isinstance(device, dict) or set(device) != {'patient_id', 'device_id', 'parameters'}:
            raise ValueError('Invalid device registration')
        for key in ('patient_id', 'device_id'):
            if not isinstance(device[key], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', device[key]):
                raise ValueError('Invalid device or patient identifier')
        if device['device_id'] in seen:
            raise ValueError('A registered device must belong to exactly one patient')
        seen.add(device['device_id'])
        parameters = device['parameters']
        if not isinstance(parameters, list) or not parameters or any(not isinstance(p, str) or p not in PARAMETER_DEFINITIONS for p in parameters) or len(set(parameters)) != len(parameters):
            raise ValueError('Invalid expected parameter list')
    return policy


class ConnectionMonitor:
    def __init__(self, policy, patients, *, now=None):
        self.policy = deepcopy(policy)
        self.patient_ids = set(patients)
        self.devices = {}
        self.explicit = {d['patient_id'] for d in policy['devices'] if d['patient_id'] in patients}
        self.now = now or (lambda: datetime.now(timezone.utc))
        for device in policy['devices']:
            if device['patient_id'] in patients:
                self._register(device['patient_id'], device['device_id'], device['parameters'], self.now())

    def _register(self, pid, did, parameters, now):
        self.devices[(pid, did)] = dict(patient_id=pid, device_id=did, parameters=list(parameters),
            started_at=now.isoformat(), last_seen_at=None, parameter_timestamps={}, status='WAITING',
            missing_parameters=list(parameters), recovery_after=None, episodes={})

    def restore(self, snapshots):
        for saved in snapshots:
            key = (saved['patient_id'], saved['device_id'])
            if key[0] not in self.patient_ids:
                continue
            if key in self.devices:
                parameters = self.devices[key]['parameters']
                self.devices[key] = deepcopy(saved)
                self.devices[key]['parameters'] = parameters
            elif key[0] not in self.explicit:
                self.devices[key] = deepcopy(saved)

    @staticmethod
    def _time(value):
        return datetime.fromisoformat(value) if value else None

    def _open(self, device, kind, now, changes, missing=None):
        if kind in device['episodes']:
            return
        event = TechnicalEvent(str(uuid4()), kind,
            'Aucune nouvelle mesure valide du capteur' if kind == 'DISCONNECTED' else 'Paramètres attendus absents ou anciens',
            device['patient_id'], device['device_id'], timestamp=now, status='ACTIVE',
            details={'missing_parameters': missing or [], 'timeout_seconds': self.policy['timeout_seconds']})
        device['episodes'][kind] = event_record(event)
        device['recovery_after'] = now.isoformat()
        changes.append(event)

    def _resolve(self, device, kind, now, changes):
        event = event_from_record(device['episodes'].pop(kind))
        event.status = 'RESOLVED'
        event.details['resolved_at'] = now.isoformat()
        changes.append(event)
        changes.append(TechnicalEvent(str(uuid4()), 'RECOVERY', 'Réception de données fraîches rétablie',
            device['patient_id'], device['device_id'], timestamp=now,
            details={'resolved_event_id': event.event_id, 'resolved_type': kind}))

    def evaluate(self, patient, measurements, *, now=None):
        now = now or self.now()
        pid, changes = patient.patient_id, []
        for measurement in measurements:
            key = (pid, measurement.device_id)
            if key not in self.devices:
                if pid in self.explicit:
                    raise ValueError('Device not registered for this patient')
                self._register(pid, measurement.device_id, [measurement.parameter], now)
            device = self.devices[key]
            if measurement.parameter not in device['parameters']:
                if pid in self.explicit:
                    raise ValueError('Parameter not registered for this device')
                device['parameters'].append(measurement.parameter)
            previous = self._time(device['parameter_timestamps'].get(measurement.parameter))
            if previous is None or measurement.timestamp > previous:
                # Capture time, not receipt time: old or out-of-order data cannot renew liveness.
                device['parameter_timestamps'][measurement.parameter] = measurement.timestamp.isoformat()
                device['last_seen_at'] = max(device['parameter_timestamps'].values(), key=datetime.fromisoformat)
        devices = [d for (p, _), d in self.devices.items() if p == pid]
        for device in devices:
            if not patient.monitoring_enabled:
                device['status'] = 'PAUSED'
                continue
            last = self._time(device['last_seen_at'])
            timeout = self.policy['timeout_seconds']
            start = self._time(device['started_at'])
            disconnected = (now - (last or start)).total_seconds() >= (timeout if last else self.policy['startup_grace_seconds'])
            if disconnected:
                self._open(device, 'DISCONNECTED', now, changes)
                device['status'] = 'DISCONNECTED'
            elif 'DISCONNECTED' in device['episodes']:
                cutoff = self._time(device['episodes']['DISCONNECTED']['timestamp'])
                if last and last > cutoff:
                    self._resolve(device, 'DISCONNECTED', now, changes)
            barrier = self._time(device['recovery_after'])
            missing = [p for p in device['parameters']
                if not (moment := self._time(device['parameter_timestamps'].get(p)))
                or (now - moment).total_seconds() >= timeout or (barrier and moment <= barrier)]
            device['missing_parameters'] = missing
            if 'DISCONNECTED' not in device['episodes']:
                if missing:
                    if (now - start).total_seconds() >= self.policy['startup_grace_seconds']:
                        self._open(device, 'MISSING_DATA', now, changes, missing)
                    device['status'] = 'DEGRADED' if last else 'WAITING'
                else:
                    if 'MISSING_DATA' in device['episodes']:
                        self._resolve(device, 'MISSING_DATA', now, changes)
                    device['status'] = 'CONNECTED'
            else:
                device['status'] = 'DISCONNECTED'
        connected = not any(d['status'] == 'DISCONNECTED' for d in devices)
        complete = bool(devices) and all(d['status'] == 'CONNECTED' for d in devices)
        return connected, complete, changes

    def snapshots(self, patient_id=None):
        return deepcopy([device for (pid, _), device in self.devices.items() if patient_id is None or pid == patient_id])
