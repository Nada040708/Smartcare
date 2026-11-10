from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from src.domain import (Patient, Measurement, ThresholdRule, CombinedRule, Condition,
                        TrendRule, ClinicalProfile, MonitoringState)
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.processing import AnomalyDetector, DataValidator, AlertEngine, MonitoringStateManager
from src.repositories import AlertRepository


def threshold(rule_id='hr', parameter='heart_rate', severity='WARNING'):
    return ThresholdRule(rule_id=rule_id, parameter=parameter, operator='>', threshold=100,
                         severity=severity, message='Seuil de démonstration')


class Pipeline:
    def __init__(self, rules=None):
        self.now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        self.ids = count()
        self.patient = Patient('P001', 'Patient 1')
        self.detector = AnomalyDetector(DataValidator(now=lambda: self.now),
                                        common_rules=rules if rules is not None else [threshold()])
        self.engine = AlertEngine()
        self.states = MonitoringStateManager()
        self.repository = AlertRepository()

    def reading(self, parameter, value, patient=None):
        return Measurement(str(next(self.ids)), (patient or self.patient).patient_id,
                           parameter=parameter, value=value, device_id='SIM', timestamp=self.now,
                           unit=PARAMETER_DEFINITIONS[parameter].unit)

    def consume(self, measurements, patient=None, connected=True):
        patient = patient or self.patient
        report = self.detector.evaluate_batch(measurements, patient)
        for alert in self.engine.process(report, connected=connected):
            self.repository.save(alert)
        state = self.states.evaluate_state(report, self.engine.get_active(), connected=connected)
        return report, state

    def cycle(self, values=None, *, seconds=1, patient=None, connected=True):
        self.now += timedelta(seconds=seconds)
        return self.consume([self.reading(p, v, patient) for p, v in (values or {}).items()],
                            patient=patient, connected=connected)


def test_persistent_anomaly_recovery_and_new_episode():
    p = Pipeline()
    assert p.cycle({'heart_rate': 80})[1] == MonitoringState.NORMAL
    assert p.cycle({'heart_rate': 140})[1] == MonitoringState.ALERT
    first = p.repository.getActive()[0]
    opened = first.timestamp
    p.cycle({'heart_rate': 150})
    assert p.repository.getHistory() == [first]
    assert first.occurrences == 2 and first.last_seen_at > opened
    assert p.cycle({'heart_rate': 80})[1] == MonitoringState.ALERT
    assert first.recovery_count == 1
    assert p.cycle({'heart_rate': 82})[1] == MonitoringState.NORMAL
    assert first.status == 'RESOLVED'
    assert first.resolved_at == p.now and first.resolution_reason == 'RECOVERY_CONFIRMED'
    assert first.recovery_measurement_ids != first.measurement_ids
    p.cycle({'heart_rate': 140})
    second = p.repository.getActive()[0]
    assert second.alert_id != first.alert_id and second.occurrences == 1
    assert len(p.repository.getHistory()) == 2


def test_duplicates_late_samples_report_replays_and_unrelated_data_cannot_confirm_recovery():
    p = Pipeline()
    anomaly_report, _ = p.cycle({'heart_rate': 140})
    p.now += timedelta(seconds=1)
    normal = p.reading('heart_rate', 80)
    normal_report, _ = p.consume([normal])
    alert = p.repository.getActive()[0]
    assert alert.recovery_count == 1
    for report in (normal_report, anomaly_report, normal_report):
        assert p.engine.process(report) == []
    assert p.consume([normal])[0].rules[0].fresh is False
    p.cycle({'temperature': 37})
    late = p.reading('heart_rate', 75)
    late.timestamp = normal.timestamp - timedelta(seconds=1)
    p.consume([late])
    assert alert.occurrences == 1 and alert.recovery_count == 1
    assert p.cycle({'heart_rate': 81})[1] == MonitoringState.NORMAL


def test_anomaly_interrupts_recovery_confirmation():
    p = Pipeline()
    for value in (140, 80, 145, 81):
        p.cycle({'heart_rate': value})
    assert p.repository.getActive()[0].recovery_count == 1
    p.cycle({'heart_rate': 82})
    assert not p.repository.getActive()


def test_expired_data_preserves_alert_and_restarts_recovery():
    p = Pipeline()
    p.cycle({'heart_rate': 140})
    p.cycle({'heart_rate': 80})
    report, state = p.cycle(seconds=121)
    alert = p.repository.getActive()[0]
    assert report.rules[0].status == 'UNKNOWN'
    assert state == MonitoringState.ALERT and alert.recovery_count == 0
    p.cycle({'heart_rate': 81})
    assert alert.status == 'ACTIVE'
    p.cycle({'heart_rate': 82})
    assert alert.status == 'RESOLVED'


def test_no_data_is_surveillance_and_not_normal_or_an_automatic_disconnect():
    p = Pipeline()
    assert p.states.get_state('P001') == MonitoringState.SURVEILLANCE
    assert p.cycle()[1] == MonitoringState.SURVEILLANCE
    assert p.cycle({'heart_rate': 80})[1] == MonitoringState.NORMAL
    assert p.cycle(seconds=121)[1] == MonitoringState.SURVEILLANCE


def test_incomplete_coverage_does_not_report_normal():
    p = Pipeline([threshold(), threshold('glucose', 'glucose')])
    assert p.cycle({'heart_rate': 80})[1] == MonitoringState.SURVEILLANCE
    assert p.cycle({'glucose': 90})[1] == MonitoringState.NORMAL


@pytest.mark.parametrize('severity,state', [('INFO', 'SURVEILLANCE'), ('WARNING', 'ALERT'), ('CRITICAL', 'CRITICAL')])
def test_states_follow_configured_severity(severity, state):
    p = Pipeline([threshold(severity=severity)])
    assert p.cycle({'heart_rate': 140})[1].value == state


def test_patient_isolation_and_critical_priority_then_deescalation():
    p = Pipeline([threshold(), threshold('glucose', 'glucose', 'CRITICAL')])
    other = Patient('P002', 'Patient 2')
    assert p.cycle({'heart_rate': 140, 'glucose': 150})[1] == MonitoringState.CRITICAL
    assert p.cycle({'heart_rate': 80, 'glucose': 90}, patient=other)[1] == MonitoringState.NORMAL
    assert p.states.get_state('P001') == MonitoringState.CRITICAL
    p.cycle({'glucose': 90})
    assert p.cycle({'glucose': 91})[1] == MonitoringState.ALERT
    assert len(p.engine.get_active('P001')) == 1
    assert not p.engine.get_active('P002')


def test_disabled_monitoring_retains_alert_and_resets_recovery():
    p = Pipeline()
    p.cycle({'heart_rate': 140})
    p.cycle({'heart_rate': 80})
    p.patient.monitoring_enabled = False
    report, state = p.cycle()
    assert not report.enabled and not report.rules
    assert state == MonitoringState.ALERT
    assert p.engine.get_active()[0].recovery_count == 0
    p.patient.monitoring_enabled = True
    p.cycle({'heart_rate': 81})
    assert p.engine.get_active()
    assert p.cycle({'heart_rate': 82})[1] == MonitoringState.NORMAL


def test_removing_profile_does_not_resolve_existing_episode():
    p = Pipeline([])
    profile = ClinicalProfile('demo', 'Démo', 'Profil de test', ['heart_rate'], rules=[threshold()])
    p.patient.add_profile(profile)
    p.cycle({'heart_rate': 140})
    p.patient.remove_profile(profile)
    assert p.cycle({'heart_rate': 80})[1] == MonitoringState.ALERT
    alert = p.engine.resolve_alert('P001', 'hr', timestamp=p.now, reason='RULE_REMOVED')
    p.repository.save(alert)
    assert alert.resolution_reason == 'RULE_REMOVED'
    assert p.cycle()[1] == MonitoringState.SURVEILLANCE


def combined():
    return CombinedRule(rule_id='combo', severity='CRITICAL', message='Combinaison démo',
                        window_seconds=30, max_skew_seconds=5,
                        conditions=(Condition('heart_rate', '>', 100), Condition('spo2', '<', 95)))


def test_combined_recovery_requires_renewal_of_each_parameter_per_confirmation():
    p = Pipeline([combined()])
    p.cycle({'heart_rate': 140, 'spo2': 90})
    alert = p.engine.get_active()[0]
    p.cycle({'heart_rate': 80})
    assert alert.recovery_count == 0  # SpO2 is still the triggering observation.
    p.cycle({'spo2': 98})
    assert alert.recovery_count == 1
    p.cycle({'spo2': 99})
    assert alert.recovery_count == 1  # One HR sample cannot confirm twice.
    p.cycle({'heart_rate': 81})
    assert alert.status == 'RESOLVED'


def test_desynchronized_combination_is_unknown_not_recovered():
    p = Pipeline([combined()])
    p.cycle({'heart_rate': 140, 'spo2': 90})
    report, state = p.cycle({'heart_rate': 80}, seconds=6)
    assert report.rules[0].status == 'UNKNOWN' and state == MonitoringState.CRITICAL
    p.cycle({'heart_rate': 81, 'spo2': 98})
    assert p.engine.get_active()[0].recovery_count == 1
    assert p.cycle({'heart_rate': 82, 'spo2': 99})[1] == MonitoringState.NORMAL


def test_synchronized_readings_received_separately_after_a_gap_can_confirm_recovery():
    p = Pipeline([combined()])
    p.cycle({'heart_rate': 140, 'spo2': 90})
    p.now += timedelta(seconds=31)
    hr, spo2 = p.reading('heart_rate', 80), p.reading('spo2', 98)
    p.now += timedelta(milliseconds=100)
    assert p.consume([hr])[0].rules[0].status == 'UNKNOWN'
    p.now += timedelta(milliseconds=100)
    p.consume([spo2])
    assert p.engine.get_active()[0].recovery_count == 1
    assert p.cycle({'heart_rate': 81, 'spo2': 99})[1] == MonitoringState.NORMAL


def test_trend_needs_enough_data_to_clear_and_gaps_are_unknown():
    rule = TrendRule(rule_id='trend', severity='WARNING', message='Tendance démo',
                     parameter='systolic_bp', minimum_delta=15, window_seconds=60,
                     min_samples=3, min_span_seconds=10, max_gap_seconds=10)
    p = Pipeline([rule])
    assert p.cycle({'systolic_bp': 110})[1] == MonitoringState.SURVEILLANCE
    p.cycle({'systolic_bp': 120}, seconds=5)
    assert p.cycle({'systolic_bp': 130}, seconds=5)[1] == MonitoringState.ALERT
    p.cycle({'systolic_bp': 120}, seconds=5)
    assert p.engine.get_active()[0].recovery_count == 1
    report, _ = p.cycle({'systolic_bp': 115}, seconds=15)
    assert report.rules[0].status == 'UNKNOWN'
    assert p.engine.get_active()[0].recovery_count == 0
    p.cycle({'systolic_bp': 110}, seconds=61)
    p.cycle({'systolic_bp': 110}, seconds=5)
    p.cycle({'systolic_bp': 110}, seconds=5)
    assert p.engine.get_active()[0].recovery_count == 1
    assert p.cycle({'systolic_bp': 110}, seconds=5)[1] == MonitoringState.NORMAL


def test_disconnection_preserves_clinical_alerts_and_reconnection_needs_new_data():
    p = Pipeline()
    p.cycle({'heart_rate': 140})
    assert p.cycle(connected=False)[1] == MonitoringState.DISCONNECTED
    assert len(p.engine.get_active()) == 1
    assert p.cycle()[1] == MonitoringState.ALERT
    p.cycle({'heart_rate': 80})
    assert p.cycle({'heart_rate': 82})[1] == MonitoringState.NORMAL
    assert p.cycle(connected=False)[1] == MonitoringState.DISCONNECTED
    assert p.cycle()[1] == MonitoringState.SURVEILLANCE  # Cached normal before disconnect.
    assert p.cycle({'heart_rate': 81})[1] == MonitoringState.NORMAL


def test_return_to_normal_cannot_override_alert_or_replay_old_normal_report():
    p = Pipeline()
    normal, _ = p.cycle({'heart_rate': 80})
    abnormal, _ = p.cycle({'heart_rate': 140})
    assert p.states.return_to_normal(abnormal, p.engine.get_active()) == MonitoringState.ALERT
    assert p.states.return_to_normal(normal, []) == MonitoringState.ALERT


def test_even_short_explicit_disconnection_resets_recovery_confirmations():
    p = Pipeline()
    p.cycle({'heart_rate': 140})
    p.cycle({'heart_rate': 80})
    alert = p.engine.get_active()[0]
    assert alert.recovery_count == 1
    p.cycle(connected=False)
    assert alert.recovery_count == 0
    p.cycle({'heart_rate': 81})
    assert alert.status == 'ACTIVE' and alert.recovery_count == 1
    assert p.cycle({'heart_rate': 82})[1] == MonitoringState.NORMAL


def test_same_message_for_two_rules_produces_two_episodes_and_upserts_by_id():
    p = Pipeline([threshold(), threshold('glucose', 'glucose')])
    p.cycle({'heart_rate': 140, 'glucose': 150})
    p.cycle({'heart_rate': 145, 'glucose': 160})
    assert len(p.repository.getHistory()) == 2
    assert all(a.occurrences == 2 for a in p.repository.getActive())


@pytest.mark.parametrize('count', [0, -1, True, 1.5])
def test_invalid_recovery_configuration(count):
    with pytest.raises(ValueError):
        AlertEngine(recovery_confirmations=count)


def test_configurable_one_confirmation_and_manual_resolution_is_idempotent():
    p = Pipeline()
    p.engine = AlertEngine(recovery_confirmations=1)
    p.cycle({'heart_rate': 140})
    alert = p.engine.get_active()[0]
    p.cycle({'heart_rate': 80})
    assert alert.status == 'RESOLVED'
    resolved_at = alert.resolved_at
    alert.resolve(timestamp=p.now + timedelta(seconds=10))
    assert alert.resolved_at == resolved_at and alert.resolution_reason == 'RECOVERY_CONFIRMED'


def test_invalid_measurement_cannot_resolve_or_mutate_alert():
    p = Pipeline()
    p.cycle({'heart_rate': 140})
    invalid = p.reading('heart_rate', 80)
    invalid.quality = 'invalid'
    with pytest.raises(ValueError):
        p.consume([invalid])
    assert p.engine.get_active()[0].recovery_count == 0


def test_replacing_detector_requires_explicit_lifecycle_restart():
    p = Pipeline()
    p.cycle({'heart_rate': 140})
    replacement = AnomalyDetector(DataValidator(now=lambda: p.now), common_rules=[threshold()])
    report = replacement.evaluate_batch([p.reading('heart_rate', 80)], p.patient)
    with pytest.raises(ValueError, match='same detector'):
        p.engine.process(report)
    with pytest.raises(ValueError, match='same detector'):
        p.states.evaluate_state(report, [])
