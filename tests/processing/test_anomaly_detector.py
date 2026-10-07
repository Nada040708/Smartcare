from src.domain.measurement import Measurement
from src.processing.anomaly_detector import AnomalyDetector


def test_detect_high_heart_rate():
    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={
            "heart_rate": 120.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    detector = AnomalyDetector()
    anomalies = detector.detect(measurement)

    assert any(
        anomaly["type"] == "high_heart_rate"
        for anomaly in anomalies
    )


def test_detect_low_spo2():
    measurement = Measurement(
        measurement_id="M002",
        patient_id="P001",
        values={
            "heart_rate": 80.0,
            "spo2": 90.0,
            "temperature": 36.7,
        },
    )

    detector = AnomalyDetector()
    anomalies = detector.detect(measurement)

    assert any(
        anomaly["type"] == "low_spo2"
        for anomaly in anomalies
    )


def test_detect_high_temperature():
    measurement = Measurement(
        measurement_id="M003",
        patient_id="P001",
        values={
            "heart_rate": 80.0,
            "spo2": 98.0,
            "temperature": 39.0,
        },
    )

    detector = AnomalyDetector()
    anomalies = detector.detect(measurement)

    assert any(
        anomaly["type"] == "high_temperature"
        for anomaly in anomalies
    )


def test_detect_combined_anomaly():
    measurement = Measurement(
        measurement_id="M004",
        patient_id="P001",
        values={
            "heart_rate": 120.0,
            "spo2": 90.0,
            "temperature": 36.7,
        },
    )

    detector = AnomalyDetector()

    combined = detector.detect_combined_anomaly(measurement)

    assert combined is not None
    assert combined["type"] == "combined_cardiopulmonary_anomaly"


def test_no_anomaly():
    measurement = Measurement(
        measurement_id="M005",
        patient_id="P001",
        values={
            "heart_rate": 80.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    detector = AnomalyDetector()
    anomalies = detector.detect(measurement)

    assert anomalies == []