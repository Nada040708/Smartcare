"""Stateful, patient-isolated evaluation of validated scalar measurements."""
from collections import OrderedDict
from copy import deepcopy
from datetime import timedelta
import json
from uuid import uuid4

from src.domain.measurement import Measurement
from src.domain.patient import Patient
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.domain.monitoring_rule import MonitoringRule, RuleContext
from src.domain.monitoring_evaluation import MonitoringEvaluation, RuleEvaluation
from src.domain.rule_catalog import load_rules
from .data_validator import DataValidator, parse_timestamp


class AnomalyDetector:
    def __init__(self, validator=None, common_rules=None, max_history=2048):
        if isinstance(max_history,bool) or not isinstance(max_history,int) or max_history < 3:
            raise ValueError('max_history must be an integer >= 3')
        self.validator = validator or DataValidator()
        self.common_rules = load_rules('common') if common_rules is None else list(common_rules)
        self.max_history = max_history
        self._history = {}
        self._seen = {}
        self._source_id = str(uuid4())
        self._sequence = 0

    def _report(self, patient, now, evaluations=()):
        self._sequence += 1
        return MonitoringEvaluation(self._source_id, self._sequence, patient.patient_id,
                                    now, patient.monitoring_enabled, tuple(evaluations))

    def clear_patient(self, patient_id):
        self._history.pop(patient_id,None)
        self._seen.pop(patient_id,None)

    def _rules(self, patient):
        selected = {}
        sources = [('common',self.common_rules)] + [(p.profile_id,p.get_rules()) for p in patient.profiles]
        for profile_id,rules in sources:
            for rule in rules:
                if not isinstance(rule,MonitoringRule):
                    raise TypeError('Profiles must contain MonitoringRule objects')
                if rule.window_seconds > self.validator.policy['max_age_seconds']:
                    raise ValueError('Rule window exceeds validated history retention')
                if rule.rule_id in selected:
                    previous,profile_ids = selected[rule.rule_id]
                    if previous != rule:
                        raise ValueError(f'Conflicting definitions for rule {rule.rule_id}')
                    if profile_id not in profile_ids:
                        profile_ids.append(profile_id)
                else:
                    selected[rule.rule_id] = (rule,[profile_id])
        return selected.values()

    def detect(self, measurement, patient=None) -> list[dict]:
        if not isinstance(measurement,Measurement):
            raise TypeError('measurement must be a Measurement')
        patient = patient or Patient(measurement.patient_id,measurement.patient_id)
        if measurement.parameter is None:
            if not self.validator.validate(measurement):
                raise ValueError('Invalid legacy measurement')
            scalars = [Measurement(
                f'{measurement.measurement_id}:{name}',measurement.patient_id,
                parameter=name,value=value,unit=PARAMETER_DEFINITIONS[name].unit,
                device_id='LEGACY_ADAPTER',device_type='legacy_adapter',
                timestamp=measurement.timestamp,quality=measurement.quality,
                reading_id=measurement.measurement_id,
            ) for name,value in measurement.values.items()]
        else:
            scalars = [measurement]
        return self.detect_batch(scalars,patient)

    def detect_payload(self, payload, patient, topic=None) -> list[dict]:
        return self.evaluate_payload(payload, patient, topic=topic).anomalies

    def evaluate_payload(self, payload, patient, topic=None) -> MonitoringEvaluation:
        result = self.validator.validate_payload(payload,topic=topic)
        if not result.accepted:
            raise ValueError(f'Invalid received measurement: {result.to_dict()}')
        data = json.loads(payload) if isinstance(payload,(str,bytes)) else payload
        measurement = Measurement(
            data['measurement_id'],data['patient_id'],device_id=data['device_id'],
            parameter=data['parameter'],value=data['value'],unit=data['unit'],
            timestamp=parse_timestamp(data['timestamp']),quality=data['quality'],
            reading_id=data['reading_id'],device_type=data['ieee11073_metadata']['device_type'],
        )
        return self.evaluate_batch([measurement],patient)

    def detect_batch(self, measurements, patient) -> list[dict]:
        return self.evaluate_batch(measurements, patient).anomalies

    def evaluate_batch(self, measurements, patient) -> MonitoringEvaluation:
        """Atomically ingest a cycle, then evaluate each relevant rule once."""
        if not isinstance(patient,Patient):
            raise TypeError('patient must be a Patient')
        if not patient.monitoring_enabled:
            self.clear_patient(patient.patient_id)
            return self._report(patient, self.validator.now())
        incoming = list(measurements)
        rules = list(self._rules(patient))
        for measurement in incoming:
            if not isinstance(measurement,Measurement) or measurement.parameter is None:
                raise ValueError('detect_batch requires scalar measurements')
            if measurement.patient_id != patient.patient_id:
                raise ValueError('Measurement/patient mismatch')
            if not self.validator.validate(measurement):
                raise ValueError('Invalid or stale measurement; history was not changed')
        now = self.validator.now()
        cutoff = now-timedelta(seconds=self.validator.policy['max_age_seconds'])
        history = deepcopy([m for m in self._history.get(patient.patient_id,[]) if m.timestamp >= cutoff])
        seen = OrderedDict((key,value) for key,value in self._seen.get(patient.patient_id,{}).items() if value['timestamp'] >= cutoff)
        added_ids = set()
        for measurement in sorted(incoming,key=lambda m:m.timestamp):
            payload = measurement.to_dict()
            previous = seen.get(measurement.measurement_id)
            if previous is not None:
                if previous['payload'] != payload:
                    raise ValueError('A measurement_id was reused with different data')
                continue
            stream = [m for m in history if (m.device_id,m.parameter) == (measurement.device_id,measurement.parameter)]
            repeated = next((m for m in stream if m.reading_id == measurement.reading_id),None)
            if repeated is not None:
                previous_payload = repeated.to_dict()
                previous_payload['measurement_id'] = measurement.measurement_id
                if previous_payload != payload:
                    raise ValueError('A reading_id was reused with different data')
                continue
            if stream and measurement.timestamp <= max(m.timestamp for m in stream):
                continue  # Late/equal-time samples cannot rewrite the current stream.
            history.append(deepcopy(measurement))
            added_ids.add(measurement.measurement_id)
            seen[measurement.measurement_id] = {'timestamp':measurement.timestamp,'payload':deepcopy(payload)}
        history = sorted(history,key=lambda m:m.timestamp)[-self.max_history:]
        while len(seen) > self.max_history:
            seen.popitem(last=False)
        context = RuleContext(tuple(history),max([now]+[m.timestamp for m in incoming]))
        evaluations = []
        for rule,profile_ids in rules:
            evidence = rule.get_evidence(context)
            if evidence is None:
                evaluations.append(RuleEvaluation(rule.rule_id, 'UNKNOWN', False, None))
                continue
            matched = rule.evaluate(context) is not None
            fresh = bool(added_ids.intersection(m.measurement_id for m in evidence))
            values = {m.parameter:m.value for m in evidence}
            result = {
                'rule_id':rule.rule_id,'type':rule.rule_id,'kind':type(rule).__name__,
                'profile_ids':list(profile_ids),'patient_id':patient.patient_id,
                'severity':rule.severity,'message':rule.message,
                'parameter':' + '.join(rule.parameters),
                'value':next(iter(values.values())) if len(values)==1 else values,
                'timestamp':context.now.isoformat(),
                'evidence':[{
                    'measurement_id':m.measurement_id,'reading_id':m.reading_id,'device_id':m.device_id,
                    'parameter':m.parameter,'value':m.value,'unit':m.unit,'timestamp':m.timestamp.isoformat(),
                } for m in evidence],
            }
            evaluations.append(RuleEvaluation(rule.rule_id, 'MATCHED' if matched else 'CLEAR', fresh, result))
        self._history[patient.patient_id] = history
        self._seen[patient.patient_id] = seen
        return self._report(patient, context.now, evaluations)

    def detect_combined_anomaly(self, measurement, patient=None):
        return next((a for a in self.detect(measurement,patient) if a['kind']=='CombinedRule'),None)

    def detect_trend(self, measurement, patient=None):
        return [a for a in self.detect(measurement,patient) if a['kind']=='TrendRule']
