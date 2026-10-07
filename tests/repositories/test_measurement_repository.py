from src.domain.measurement import Measurement
from src.repositories.measurement_repository import MeasurementRepository


def test_save_measurement():
    repository = MeasurementRepository()

    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={
            "heart_rate": 78.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    repository.save(measurement)

    assert len(repository.measurements) == 1
    assert repository.measurements[0] is measurement


def test_get_by_patient():
    repository = MeasurementRepository()

    measurement_1 = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={"heart_rate": 78.0},
    )

    measurement_2 = Measurement(
        measurement_id="M002",
        patient_id="P002",
        values={"heart_rate": 82.0},
    )

    repository.save(measurement_1)
    repository.save(measurement_2)

    results = repository.getByPatient("P001")

    assert len(results) == 1
    assert results[0].patient_id == "P001"


def test_get_history():
    repository = MeasurementRepository()

    measurement_1 = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={"heart_rate": 78.0},
    )

    measurement_2 = Measurement(
        measurement_id="M002",
        patient_id="P001",
        values={"heart_rate": 80.0},
    )

    repository.save(measurement_1)
    repository.save(measurement_2)

    history = repository.getHistory()

    assert len(history) == 2
    assert history[0] is measurement_1
    assert history[1] is measurement_2