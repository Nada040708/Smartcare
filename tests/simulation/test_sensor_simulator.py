from src.domain.patient import Patient
from src.domain.parameters import HeartRate, SpO2, Temperature
from src.simulation import SensorSimulator
from src.simulation.strategies import (
    NormalStrategy,
    ProgressiveStrategy,
)


def test_sensor_simulator_start_stop():
    simulator = SensorSimulator(interval=1)

    assert simulator.running is False

    simulator.start()
    assert simulator.running is True

    simulator.stop()
    assert simulator.running is False


def test_generate_measurement():
    patient = Patient("P001", "Patient 1")

    patient.add_parameter(HeartRate())
    patient.add_parameter(SpO2())
    patient.add_parameter(Temperature())

    strategies = {
        "heart_rate": NormalStrategy(),
        "spo2": ProgressiveStrategy(step=1.0),
    }

    simulator = SensorSimulator()

    measurement = simulator.generate_measurement(
        patient,
        strategies,
    )

    assert measurement.patient_id == "P001"

    assert "heart_rate" in measurement.values
    assert "spo2" in measurement.values
    assert "temperature" in measurement.values

    assert measurement.validate()