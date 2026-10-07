from src.dashboard.dashboard import Dashboard
from src.domain.measurement import Measurement
from src.domain.alert import Alert
from src.repositories.measurement_repository import MeasurementRepository
from src.repositories.alert_repository import AlertRepository


def create_dashboard():
    measurement_repository = MeasurementRepository()
    alert_repository = AlertRepository()

    return Dashboard(
        measurement_repository,
        alert_repository,
    )


def test_display_measurements():
    dashboard = create_dashboard()

    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={
            "heart_rate": 78.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    dashboard.measurement_repository.save(measurement)

    measurements = dashboard.displayMeasurements()

    assert len(measurements) == 1
    assert measurements[0] is measurement


def test_display_graphs():
    dashboard = create_dashboard()

    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={
            "heart_rate": 78.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    dashboard.measurement_repository.save(measurement)

    graphs = dashboard.displayGraphs()

    assert graphs["heart_rate"] == [78.0]
    assert graphs["spo2"] == [98.0]
    assert graphs["temperature"] == [36.7]


def test_display_alerts():
    dashboard = create_dashboard()

    alert = Alert(
        alert_id="A001",
        patient_id="P001",
        severity="WARNING",
        message="High heart rate.",
    )

    dashboard.alert_repository.save(alert)

    alerts = dashboard.displayAlerts()

    assert len(alerts) == 1
    assert alerts[0] is alert


def test_display_status():
    dashboard = create_dashboard()

    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={"heart_rate": 78.0},
    )

    alert = Alert(
        alert_id="A001",
        patient_id="P001",
        severity="WARNING",
        message="High heart rate.",
    )

    dashboard.measurement_repository.save(measurement)
    dashboard.alert_repository.save(alert)

    status = dashboard.displayStatus()

    assert status["measurements_count"] == 1
    assert status["active_alerts_count"] == 1