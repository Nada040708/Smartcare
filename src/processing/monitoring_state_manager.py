"""Patient-isolated monitoring states, with conservative return to normal."""
from datetime import datetime

from src.domain.monitoring_state import MonitoringState


class MonitoringStateManager:
    def __init__(self):
        self.current_states = {}
        self._processed = {}
        self._disconnected_since = {}

    def get_state(self, patient_id):
        return self.current_states.get(patient_id, MonitoringState.SURVEILLANCE)

    def evaluate_state(self, evaluation, alerts, *, connected=True, complete=True):
        """Consume the report after AlertEngine.process, with this patient's alerts.

        connected=False is an explicit technical signal, not a timeout detector.
        Reconnection requires new observations before returning to NORMAL.
        """
        patient_id = evaluation.patient_id
        previous = self._processed.get(patient_id)
        if previous:
            if previous[0] != evaluation.source_id:
                raise ValueError('Use the same detector for this patient and state manager')
            if evaluation.sequence <= previous[1]:
                return self.get_state(patient_id)
        active = [a for a in alerts if a.patient_id == patient_id and a.status == 'ACTIVE']
        if not connected:
            self._disconnected_since[patient_id] = evaluation.timestamp
            state = MonitoringState.DISCONNECTED
        elif any(a.severity == 'CRITICAL' for a in active):
            state = MonitoringState.CRITICAL
        elif any(a.severity == 'WARNING' for a in active):
            state = MonitoringState.ALERT
        elif active or not evaluation.enabled or not evaluation.rules or not complete:
            state = MonitoringState.SURVEILLANCE
        elif all(r.status == 'CLEAR' for r in evaluation.rules) and self._has_reconnected_evidence(evaluation):
            state = MonitoringState.NORMAL
        else:
            state = MonitoringState.SURVEILLANCE
        self.current_states[patient_id] = state
        self._processed[patient_id] = (evaluation.source_id, evaluation.sequence)
        return state

    def _has_reconnected_evidence(self, evaluation):
        cutoff = self._disconnected_since.get(evaluation.patient_id)
        if cutoff is None:
            return True
        return all(datetime.fromisoformat(m['timestamp']) > cutoff
                   for r in evaluation.rules for m in r.result['evidence'])

    def return_to_normal(self, evaluation, alerts):
        """Reevaluate with all guards; never force NORMAL over active alerts."""
        return self.evaluate_state(evaluation, alerts)
