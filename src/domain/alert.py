from datetime import datetime


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
    ):
        self.alert_id = alert_id
        self.patient_id = patient_id
        self.severity = severity
        self.message = message
        self.timestamp = timestamp or datetime.now()
        self.status = status

    def resolve(self) -> None:
        self.status = "RESOLVED"