from src.domain.alert import Alert


class AlertRepository:
    """
    Stores and retrieves alerts.
    """

    def __init__(self):
        self.alerts: list[Alert] = []

    def save(self, alert: Alert) -> None:
        for index, existing_alert in enumerate(self.alerts):
            if existing_alert.alert_id == alert.alert_id:
                self.alerts[index] = alert
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

    def count(self, *, active=False):
        return len(self.getActive()) if active else len(self.alerts)
