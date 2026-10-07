from src.domain.measurement import Measurement
from src.processing.data_validator import DataValidator


def test_valid_measurement():
    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={
            "heart_rate": 78.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    validator = DataValidator()

    assert validator.validate(measurement)


def test_invalid_format():
    measurement = Measurement(
        measurement_id="M002",
        patient_id="P001",
        values={
            "heart_rate": "high",
        },
    )

    validator = DataValidator()

    assert not validator.validate_format(measurement)
    assert not validator.validate(measurement)


def test_invalid_range():
    measurement = Measurement(
        measurement_id="M003",
        patient_id="P001",
        values={
            "heart_rate": 300.0,
        },
    )

    validator = DataValidator()

    assert not validator.validate_range(measurement)
    assert not validator.validate(measurement)


def test_valid_boundary():
    measurement = Measurement(
        measurement_id="M004",
        patient_id="P001",
        values={
            "heart_rate": 220.0,
            "spo2": 70.0,
            "temperature": 45.0,
        },
    )

    validator = DataValidator()

    assert validator.validate(measurement)