from src.domain.alert import Alert
from uuid import uuid4
from datetime import datetime
from copy import deepcopy

from src.domain.monitoring_evaluation import MonitoringEvaluation


class AlertEngine:
    """Maintain one active alert episode per patient and rule."""

    def __init__(self, recovery_confirmations=2, *, auto_resolve=True):
        if isinstance(recovery_confirmations, bool) or not isinstance(recovery_confirmations, int) or recovery_confirmations < 1:
            raise ValueError('recovery_confirmations must be a positive integer')
        self.recovery_confirmations = recovery_confirmations
        self.auto_resolve = auto_resolve
        self._active = {}
        self._processed = {}
        self._recovery_watermarks = {}
        self._recovery_not_before = {}

    def restore_active(self, alerts, *, restarted_at):
        """Resume episodes, requiring entirely new recovery evidence after restart."""
        if self._active or self._processed:
            raise ValueError('Restore alerts only into a new engine')
        restored = {}
        for alert in alerts:
            if alert.status != 'ACTIVE' or not alert.rule_id:
                raise ValueError('Only active rule-based alerts can be restored')
            key = (alert.patient_id, alert.rule_id)
            if key in restored:
                raise ValueError('Duplicate active patient/rule episode')
            restored[key] = deepcopy(alert)
            restored[key].recovery_count = 0
            restored[key].recovery_measurement_ids = []
        self._active = restored
        self._recovery_not_before = {key: restarted_at for key in restored}
        return self.get_active()

    def get_active(self, patient_id=None):
        return [a for a in self._active.values() if a.status == 'ACTIVE'
                and (patient_id is None or a.patient_id == patient_id)]

    def process(self, evaluation: MonitoringEvaluation, *, connected=True, recovery_allowed=True) -> list[Alert]:
        """Apply one detector report, returning created/updated/resolved episodes.

        Calls are sequential. Each patient uses one detector for this engine's
        lifetime; the source and sequence prevent report replay from confirming recovery.
        """
        patient_id = evaluation.patient_id
        previous = self._processed.get(patient_id)
        if previous:
            if previous[0] != evaluation.source_id:
                raise ValueError('Use the same detector for this patient and engine')
            if evaluation.sequence <= previous[1]:
                return []
        changes = []
        observations = {r.rule_id: r for r in evaluation.rules} if evaluation.enabled else {}
        # A suspended or removed rule does not prove recovery.
        for alert in self.get_active(patient_id):
            observation = observations.get(alert.rule_id)
            if observation is None or observation.status == 'UNKNOWN' or not connected or not recovery_allowed:
                key = (patient_id, alert.rule_id)
                # Explicit interruption is a time barrier. An incomplete network
                # delivery only resets the count: its remaining synchronized
                # samples may have been captured before this report was received.
                if not connected or not evaluation.enabled:
                    self._recovery_not_before[key] = evaluation.timestamp
                    self._recovery_watermarks[key] = {
                        parameter: max(timestamp, evaluation.timestamp)
                        for parameter, timestamp in self._recovery_watermarks.get(key, {}).items()
                    }
                if alert.recovery_count:
                    alert.recovery_count = 0
                    alert.recovery_measurement_ids = []
                    changes.append(alert)
        for observation in observations.values():
            if not observation.fresh or observation.status == 'UNKNOWN':
                continue
            result = observation.result
            if observation.status == 'MATCHED':
                changes.extend(self.evaluate(patient_id, [result]))
                continue
            if not connected or not recovery_allowed:
                continue
            key = (patient_id, observation.rule_id)
            alert = self._active.get(key)
            if alert is None or alert.status != 'ACTIVE':
                continue
            latest = self._latest_timestamps(result)
            watermarks = self._recovery_watermarks.get(key, {})
            restart = self._recovery_not_before.get(key)
            if restart is not None and any(timestamp <= restart for timestamp in latest.values()):
                continue
            if any(parameter in watermarks and timestamp <= watermarks[parameter]
                   for parameter, timestamp in latest.items()):
                continue
            self._recovery_watermarks[key] = latest
            alert.recovery_count += 1
            alert.recovery_measurement_ids = [m['measurement_id'] for m in result['evidence']]
            if alert.recovery_count >= self.recovery_confirmations:
                if self.auto_resolve:
                    self.resolve_alert(patient_id, observation.rule_id, evaluation.timestamp, 'RECOVERY_CONFIRMED')
                else:
                    # Physiological recovery is useful context, but a clinician
                    # remains responsible for closing the visible episode.
                    alert.recovery_count = self.recovery_confirmations
            changes.append(alert)
        self._processed[patient_id] = (evaluation.source_id, evaluation.sequence)
        return changes

    def resolve_alert(self, patient_id, rule_id, timestamp=None, reason='MANUAL'):
        alert = self._active.pop((patient_id, rule_id), None)
        self._recovery_watermarks.pop((patient_id, rule_id), None)
        self._recovery_not_before.pop((patient_id, rule_id), None)
        if alert is not None:
            alert.resolve(timestamp=timestamp, reason=reason)
        return alert

    @staticmethod
    def _latest_timestamps(result):
        latest = {}
        for measurement in result.get('evidence', []):
            parameter = measurement['parameter']
            timestamp = datetime.fromisoformat(measurement['timestamp'])
            latest[parameter] = max(timestamp, latest.get(parameter, timestamp))
        return latest

    def evaluate(
        self,
        patient_id: str,
        anomalies: list[dict],
    ) -> list[Alert]:

        alerts = []

        # Validate the whole list before mutating any active episode.
        for anomaly in anomalies:
            if anomaly.get('patient_id', patient_id) != patient_id:
                raise ValueError('Anomaly/patient mismatch')
            self.determine_severity(anomaly)

        for index, anomaly in enumerate(anomalies, start=1):
            if anomaly.get("patient_id", patient_id) != patient_id:
                raise ValueError("Anomaly/patient mismatch")
            severity = self.determine_severity(anomaly)

            key = (patient_id, anomaly.get('rule_id') or anomaly['type'])
            alert = self._active.get(key)
            if alert is None or alert.status != 'ACTIVE':
                alert = self.create_alert(patient_id, anomaly, severity, index)
                self._active[key] = alert
            else:
                alert.severity = severity
                alert.message = anomaly['message']
                alert.profile_ids = list(anomaly.get('profile_ids', []))
                alert.measurement_ids = [m['measurement_id'] for m in anomaly.get('evidence', [])]
                alert.last_seen_at = self._timestamp(anomaly)
                alert.occurrences += 1
                alert.recovery_count = 0
                alert.recovery_measurement_ids = []

            self._recovery_watermarks[key] = self._latest_timestamps(anomaly)

            alerts.append(alert)

        return alerts

    @staticmethod
    def _timestamp(anomaly):
        value = anomaly.get('timestamp')
        if value is None:
            from datetime import timezone
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(value)

    def determine_severity(self, anomaly: dict) -> str:
        if "severity" in anomaly:
            if anomaly["severity"] not in {"INFO", "WARNING", "CRITICAL"}:
                raise ValueError("Unknown rule severity")
            return anomaly["severity"]
        anomaly_type = anomaly["type"]

        if anomaly_type == "combined_cardiopulmonary_anomaly":
            return "CRITICAL"

        if anomaly_type in {
            "high_heart_rate",
            "low_spo2",
            "high_temperature",
        }:
            return "WARNING"

        return "INFO"

    def create_alert(
        self,
        patient_id: str,
        anomaly: dict,
        severity: str,
        alert_number: int = 1,
    ) -> Alert:

        alert_id = f"A-{patient_id}-{uuid4()}"

        return Alert(
            alert_id=alert_id,
            patient_id=patient_id,
            severity=severity,
            message=anomaly["message"],
            timestamp=self._timestamp(anomaly),
            rule_id=anomaly.get("rule_id", anomaly.get("type")),
            profile_ids=anomaly.get("profile_ids", []),
            measurement_ids=[m["measurement_id"] for m in anomaly.get("evidence", [])],
            parameter=anomaly.get('parameter'),
        )
