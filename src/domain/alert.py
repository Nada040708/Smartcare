from datetime import datetime, timezone


class Alert:
    """
    Represents an alert generated from a detected anomaly.
    """

    def __init__(
        self,
        alert_id: str,
        patient_id: str,
        severity: str,
        message: str,
        timestamp: datetime | None = None,
        status: str = "ACTIVE",
        *,
        rule_id: str | None = None,
        profile_ids: list[str] | None = None,
        measurement_ids: list[str] | None = None,
        parameter: str | None = None,
    ):
        self.alert_id = alert_id
        self.patient_id = patient_id
        self.severity = severity
        self.message = message
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.status = status
        self.rule_id = rule_id
        self.profile_ids = list(profile_ids or [])
        self.measurement_ids = list(measurement_ids or [])
        self.parameter = parameter
        self.last_seen_at = self.timestamp
        self.occurrences = 1
        self.recovery_count = 0
        self.resolved_at = None
        self.resolution_reason = None
        self.recovery_measurement_ids = []

    def resolve(self, timestamp: datetime | None = None, reason: str = "MANUAL") -> None:
        if self.status == "RESOLVED":
            return
        self.status = "RESOLVED"
        self.resolved_at = timestamp or datetime.now(timezone.utc)
        self.resolution_reason = reason
