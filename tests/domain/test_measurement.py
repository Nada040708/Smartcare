from src.domain.measurement import Measurement


def test_measurement_creation():
    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={
            "heart_rate": 78.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    assert measurement.measurement_id == "M001"
    assert measurement.patient_id == "P001"
    assert measurement.values["heart_rate"] == 78.0
    assert measurement.quality == "good"


def test_measurement_validation():
    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={"heart_rate": 78.0},
    )

    assert measurement.validate()


def test_measurement_json():
    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={"heart_rate": 78.0},
    )

    data = measurement.to_json()

    assert '"measurement_id": "M001"' in data
    assert '"patient_id": "P001"' in data
    assert '"heart_rate": 78.0' in data