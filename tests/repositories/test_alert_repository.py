from src.domain.alert import Alert
from src.repositories.alert_repository import AlertRepository


def test_save_alert():
    repository = AlertRepository()

    alert = Alert(
        alert_id="A001",
        patient_id="P001",
        severity="WARNING",
        message="High heart rate.",
    )

    repository.save(alert)

    assert len(repository.alerts) == 1
    assert repository.alerts[0] is alert


def test_get_active():
    repository = AlertRepository()

    active_alert = Alert(
        alert_id="A001",
        patient_id="P001",
        severity="WARNING",
        message="High heart rate.",
    )

    resolved_alert = Alert(
        alert_id="A002",
        patient_id="P001",
        severity="WARNING",
        message="High temperature.",
    )

    resolved_alert.resolve()

    repository.save(active_alert)
    repository.save(resolved_alert)

    active_alerts = repository.getActive()

    assert len(active_alerts) == 1
    assert active_alerts[0] is active_alert


def test_get_history():
    repository = AlertRepository()

    alert_1 = Alert(
        alert_id="A001",
        patient_id="P001",
        severity="WARNING",
        message="High heart rate.",
    )

    alert_2 = Alert(
        alert_id="A002",
        patient_id="P001",
        severity="CRITICAL",
        message="Low SpO2.",
    )

    repository.save(alert_1)
    repository.save(alert_2)

    history = repository.getHistory()

    assert len(history) == 2
    assert history[0] is alert_1
    assert history[1] is alert_2