from src.domain.alert import Alert


class AlertEngine:
    """
    Evaluates detected anomalies and creates alerts.
    """

    def evaluate(
        self,
        patient_id: str,
        anomalies: list[dict],
    ) -> list[Alert]:

        alerts = []

        for index, anomaly in enumerate(anomalies, start=1):
            severity = self.determine_severity(anomaly)

            alert = self.create_alert(
                patient_id=patient_id,
                anomaly=anomaly,
                severity=severity,
                alert_number=index,
            )

            alerts.append(alert)

        return alerts

    def determine_severity(self, anomaly: dict) -> str:
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

        alert_id = f"A-{patient_id}-{alert_number}"

        return Alert(
            alert_id=alert_id,
            patient_id=patient_id,
            severity=severity,
            message=anomaly["message"],
        )