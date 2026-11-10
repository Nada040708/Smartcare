from src.processing.alert_engine import AlertEngine


def test_warning_alert():
    engine = AlertEngine()

    anomalies = [
        {
            "parameter": "heart_rate",
            "type": "high_heart_rate",
            "value": 120.0,
            "message": "Heart rate is above the normal range.",
        }
    ]

    alerts = engine.evaluate("P001", anomalies)

    assert len(alerts) == 1
    assert alerts[0].patient_id == "P001"
    assert alerts[0].severity == "WARNING"
    assert alerts[0].status == "ACTIVE"


def test_critical_combined_alert():
    engine = AlertEngine()

    anomalies = [
        {
            "parameter": "heart_rate + spo2",
            "type": "combined_cardiopulmonary_anomaly",
            "value": {
                "heart_rate": 120.0,
                "spo2": 90.0,
            },
            "message": "High heart rate combined with low SpO2.",
        }
    ]

    alerts = engine.evaluate("P001", anomalies)

    assert len(alerts) == 1
    assert alerts[0].severity == "CRITICAL"


def test_alert_resolution():
    engine = AlertEngine()

    anomaly = {
        "parameter": "temperature",
        "type": "high_temperature",
        "value": 39.0,
        "message": "Temperature is above the normal range.",
    }

    alerts = engine.evaluate("P001", [anomaly])

    alert = alerts[0]

    assert alert.status == "ACTIVE"

    alert.resolve()

    assert alert.status == "RESOLVED"


def test_multiple_alerts():
    engine = AlertEngine()

    anomalies = [
        {
            "parameter": "heart_rate",
            "type": "high_heart_rate",
            "value": 120.0,
            "message": "High heart rate.",
        },
        {
            "parameter": "temperature",
            "type": "high_temperature",
            "value": 39.0,
            "message": "High temperature.",
        },
    ]

    alerts = engine.evaluate("P001", anomalies)

    assert len(alerts) == 2
    assert alerts[0].severity == "WARNING"
    assert alerts[1].severity == "WARNING"