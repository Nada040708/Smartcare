from src.domain.measurement import Measurement
from src.domain.alert import Alert
from src.repositories.measurement_repository import MeasurementRepository
from src.repositories.alert_repository import AlertRepository


class Dashboard:
    """
    Displays measurements, alerts and system status.
    """

    def __init__(
        self,
        measurement_repository: MeasurementRepository,
        alert_repository: AlertRepository,
        state_manager=None,
    ):
        self.measurement_repository = measurement_repository
        self.alert_repository = alert_repository
        self.state_manager = state_manager

    def displayMeasurements(self) -> list[Measurement]:
        measurements = self.measurement_repository.getHistory()

        for measurement in measurements:
            print(
                f"Patient: {measurement.patient_id} | "
                f"Timestamp: {measurement.timestamp} | "
                f"Values: {measurement.values}"
            )

        return measurements

    def displayGraphs(self) -> dict:
        measurements = self.measurement_repository.getHistory()

        graphs = {
            "heart_rate": [],
            "spo2": [],
            "temperature": [],
        }

        for measurement in measurements:
            for parameter in graphs:
                if parameter in measurement.values:
                    graphs[parameter].append(
                        measurement.values[parameter]
                    )

        return graphs

    def displayAlerts(self) -> list[Alert]:
        alerts = self.alert_repository.getActive()

        for alert in alerts:
            print(
                f"Alert: {alert.alert_id} | "
                f"Patient: {alert.patient_id} | "
                f"Severity: {alert.severity} | "
                f"Message: {alert.message}"
            )

        return alerts

    def displayStatus(self) -> dict:
        status = {
            "measurements_count": self.measurement_repository.count(),
            "active_alerts_count": self.alert_repository.count(active=True),
        }
        if self.state_manager is not None:
            status['patient_states'] = {patient_id: state.value for patient_id, state in self.state_manager.current_states.items()}
        return status
