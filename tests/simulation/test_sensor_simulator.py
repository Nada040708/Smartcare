from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.domain import Patient
from src.domain.parameters import HeartRate, SpO2, Temperature, BloodPressure
from src.simulation import SensorDevice, SensorSimulator
from src.simulation.strategies import (
    GenerationStrategy, NormalStrategy, ProgressiveStrategy,
    SuddenChangeStrategy, MissingDataStrategy, RecoveryStrategy,
)


def make_simulator(patient_id="P001", strategies=None, parameters=None):
    patient = Patient(patient_id, "Patient fictif")
    for parameter in parameters if parameters is not None else [HeartRate()]:
        patient.add_parameter(parameter)
    simulator = SensorSimulator(patient, strategies=strategies)
    simulator.start()
    return simulator


def seeded_heart_rate(value=80):
    parameter = HeartRate()
    parameter.record_value(value)
    return parameter


def test_sensor_simulator_start_stop():
    simulator = SensorSimulator(Patient("P001", "Patient 1"))
    assert isinstance(simulator, SensorDevice)
    assert simulator.running is False
    assert simulator.get_status() == "STOPPED"
    assert simulator.read() == []
    simulator.start()
    assert simulator.running is True
    assert simulator.get_status() == "RUNNING"
    simulator.stop()
    assert simulator.read() == []
    assert simulator.get_status() == "STOPPED"


def test_generate_measurements():
    simulator = make_simulator(
        parameters=[HeartRate(), SpO2(), Temperature(), BloodPressure()],
        strategies={"heart_rate": NormalStrategy(60, 100)},
    )
    measurements = simulator.generate_measurements()
    assert {m.parameter for m in measurements} == {
        "heart_rate", "spo2", "temperature", "systolic_bp", "diastolic_bp",
    }
    assert all(m.validate() and m.patient_id == "P001" and m.device_id == "SIM_P001" for m in measurements)
    assert all(m.ieee11073_metadata.device_type == "simulator" for m in measurements)
    assert len({m.measurement_id for m in measurements}) == 5


def test_progression_records_fresh_time_and_unique_readings():
    simulator = make_simulator(
        parameters=[seeded_heart_rate()], strategies={"heart_rate": ProgressiveStrategy(5)},
    )
    with patch("src.domain.parameters.physiological_parameter.datetime") as clock:
        clock.now.side_effect = [
            datetime(2026, 10, 8, 16, 0, second, tzinfo=timezone.utc) for second in range(3)
        ]
        readings = [simulator.read()[0] for _ in range(3)]
    assert [m.value for m in readings] == [85, 90, 95]
    assert len({m.timestamp for m in readings}) == 3
    assert len({m.reading_id for m in readings}) == 3
    assert len({m.measurement_id for m in readings}) == 3


def test_state_is_independent_even_when_configuration_objects_are_shared():
    parameter = seeded_heart_rate()
    strategy = SuddenChangeStrategy(change=60, trigger_after=1)
    first = make_simulator("P001", parameters=[parameter], strategies={"heart_rate": strategy})
    second = make_simulator("P002", parameters=[parameter], strategies={"heart_rate": strategy})
    assert [first.read()[0].value for _ in range(3)] == [80, 140, 140]
    assert [second.read()[0].value for _ in range(3)] == [80, 140, 140]
    assert parameter.value == 80
    assert strategy.generate(80) == 80  # caller's scenario was not consumed


def test_disabled_stopped_and_failed_cycles_do_not_advance_scenarios():
    simulator = make_simulator(
        parameters=[seeded_heart_rate()], strategies={"heart_rate": ProgressiveStrategy(5)},
    )
    assert simulator.read()[0].value == 85
    simulator.patient.monitoring_enabled = False
    assert simulator.read() == []
    assert simulator.status == "DISABLED"
    simulator.patient.monitoring_enabled = True
    simulator.simulate_failure()
    assert simulator.status == "FAILED" and simulator.read() == []
    simulator.stop()
    simulator.start()
    assert simulator.read() == []  # start does not repair a failure
    simulator.restore()
    assert simulator.read()[0].value == 90
    simulator.stop()
    simulator.restore()
    assert simulator.status == "STOPPED" and simulator.read() == []


def test_missing_readings_are_omitted_and_recovery_resumes_from_last_value():
    simulator = make_simulator(
        parameters=[seeded_heart_rate(140), SpO2()],
        strategies={"heart_rate": MissingDataStrategy()},
    )
    for _ in range(2):
        assert [m.parameter for m in simulator.read()] == ["spo2"]
    assert simulator.status == "RUNNING"
    simulator.set_strategy("heart_rate", RecoveryStrategy(80, step=30))
    assert [simulator.read()[0].value for _ in range(3)] == [110, 80, 80]


def test_bp_strategy_outputs_share_one_reading_and_missing_component_omits_pair():
    pressure = BloodPressure()
    pressure.record_value({"systolic_bp": 120, "diastolic_bp": 80})
    simulator = make_simulator(parameters=[pressure], strategies={
        "systolic_bp": ProgressiveStrategy(5), "diastolic_bp": ProgressiveStrategy(2),
    })
    systolic, diastolic = simulator.read()
    assert (systolic.value, diastolic.value) == (125, 82)
    assert systolic.reading_id == diastolic.reading_id
    assert systolic.timestamp == diastolic.timestamp
    simulator.set_strategy("diastolic_bp", MissingDataStrategy())
    assert simulator.read() == []
    simulator.set_strategy("diastolic_bp", ProgressiveStrategy(2))
    systolic, diastolic = simulator.read()
    assert (systolic.value, diastolic.value) == (130, 84)


def test_invalid_cycle_rolls_back_values_and_sudden_scenario_counter():
    pressure = BloodPressure()
    pressure.record_value({"systolic_bp": 120, "diastolic_bp": 80})
    simulator = make_simulator(parameters=[seeded_heart_rate(), pressure], strategies={
        "heart_rate": SuddenChangeStrategy(change=60),
        "diastolic_bp": ProgressiveStrategy(100),
    })
    with pytest.raises(ValueError):
        simulator.read()
    simulator.set_strategy("diastolic_bp", ProgressiveStrategy(1))
    readings = simulator.read()
    assert readings[0].value == 140  # the failed cycle did not consume the jump
    assert readings[-1].value == 81


def test_removing_or_replacing_a_strategy_is_explicit():
    simulator = make_simulator(parameters=[seeded_heart_rate()], strategies={"heart_rate": MissingDataStrategy()})
    assert simulator.read() == []
    simulator.set_strategy("heart_rate", None)
    assert simulator.read()[0].validate()
    simulator.set_strategy("heart_rate", NormalStrategy(80, 80))
    assert simulator.read()[0].value == 80
    simulator.set_strategy("heart_rate", SuddenChangeStrategy(change=20))
    assert simulator.read()[0].value == 100
    simulator.set_strategy("heart_rate", SuddenChangeStrategy(change=20))
    assert simulator.read()[0].value == 120


@pytest.mark.parametrize("interval", [0, -1, True, float("nan"), float("inf")])
def test_invalid_intervals_are_rejected(interval):
    with pytest.raises(ValueError):
        SensorSimulator(Patient("P001", "Patient 1"), interval=interval)


def test_invalid_configuration_is_reported():
    with pytest.raises(ValueError, match="only once"):
        make_simulator(parameters=[HeartRate(), HeartRate()])
    with pytest.raises(ValueError, match="Unknown"):
        make_simulator(strategies={"glucose": ProgressiveStrategy()})
    simulator = make_simulator()
    with pytest.raises(TypeError):
        simulator.set_strategy("heart_rate", "normal")
    simulator.patient.patient_id = "P002"
    with pytest.raises(ValueError, match="reassigned"):
        simulator.read()


class InvalidOutputStrategy(GenerationStrategy):
    def generate(self, current_value):
        return float("nan")


def test_invalid_strategy_output_is_not_emitted():
    simulator = make_simulator(strategies={"heart_rate": InvalidOutputStrategy()})
    with pytest.raises(ValueError):
        simulator.read()
