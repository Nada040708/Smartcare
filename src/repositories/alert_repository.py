from src.domain.alert import Alert


class AlertRepository:
    """
    Stores and retrieves alerts.
    """

    def __init__(self):
        self.alerts: list[Alert] = []

    def save(self, alert: Alert) -> None:
        for existing_alert in self.alerts:
            if (
                existing_alert.patient_id == alert.patient_id
                and existing_alert.message == alert.message
                and existing_alert.status == "ACTIVE"
            ):
                return

        self.alerts.append(alert)

    def getActive(self) -> list[Alert]:
        return [
            alert
            for alert in self.alerts
            if alert.status == "ACTIVE"
        ]

    def getHistory(self) -> list[Alert]:
        return self.alerts.copy()