from unittest.mock import patch

import pytest

from src.domain import DiabetesProfile, HypertensionProfile, AnxietyProfile
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.domain.parameters import (
    HeartRate, SpO2, Temperature, BloodPressure, Glucose, RespiratoryRate, HRV, Activity,
)


SCALAR_PARAMETERS = [HeartRate, SpO2, Temperature, Glucose, RespiratoryRate, HRV, Activity]


@pytest.mark.parametrize("parameter_type", SCALAR_PARAMETERS)
def test_scalar_generation_exports_an_independent_valid_snapshot(parameter_type):
    parameter = parameter_type()
    with pytest.raises(ValueError, match="Generate"):
        parameter.to_measurements("P001", "SIM_01")

    with patch("src.domain.parameters.physiological_parameter.random.uniform", return_value=parameter.normal_min):
        value = parameter.generate()
    measurement, = parameter.to_measurements("P001", "SIM_01")
    assert measurement.validate()
    assert measurement.parameter == parameter.name
    assert measurement.unit == PARAMETER_DEFINITIONS[parameter.name].unit
    assert measurement.value == value
    assert measurement.timestamp == parameter.timestamp
    assert measurement.ieee11073_metadata.device_type == "simulator"
    previous_reading = measurement.reading_id

    with patch("src.domain.parameters.physiological_parameter.random.uniform", return_value=parameter.normal_max):
        parameter.generate()
    next_measurement, = parameter.to_measurements("P001", "SIM_01")
    assert measurement.value == value
    assert next_measurement.measurement_id != measurement.measurement_id
    assert next_measurement.reading_id != previous_reading
    assert next_measurement.value == parameter.normal_max


def test_blood_pressure_components_share_reading_and_have_distinct_metric_codes():
    parameter = BloodPressure()
    assert parameter.systolic is None
    assert not parameter.is_normal()
    with patch("src.domain.parameters.blood_pressure.random.uniform", side_effect=[120.0, 80.0]):
        values = parameter.generate()
    systolic, diastolic = parameter.to_measurements("P001", "SIM_BP_01")

    assert values == {"systolic_bp": 120.0, "diastolic_bp": 80.0}
    assert parameter.systolic == 120.0 and parameter.diastolic == 80.0
    assert systolic.value == 120.0 and diastolic.value == 80.0
    assert systolic.reading_id == diastolic.reading_id
    assert systolic.timestamp == diastolic.timestamp
    assert systolic.device_id == diastolic.device_id == "SIM_BP_01"
    assert systolic.patient_id == diastolic.patient_id == "P001"
    assert systolic.measurement_id != diastolic.measurement_id
    assert systolic.ieee11073_metadata.metric_code == "150021"
    assert diastolic.ieee11073_metadata.metric_code == "150022"
    assert systolic.ieee11073_metadata.unit_code == "266016"
    values["systolic_bp"] = 999
    assert parameter.systolic == 120.0
    assert parameter.is_normal()


@pytest.mark.parametrize("value", [
    {"systolic_bp": 80.0, "diastolic_bp": 120.0},
    {"systolic_bp": 120.0},
    {"systolic_bp": float("nan"), "diastolic_bp": 80.0},
    {"systolic_bp": 120.0, "diastolic_bp": True},
    {"systolic_bp": 120.0, "diastolic_bp": 0.0},
    120.0,
])
def test_invalid_blood_pressure_pairs_are_not_exported(value):
    parameter = BloodPressure()
    parameter.generate()
    parameter.value = value
    assert not parameter.is_normal()
    with pytest.raises(ValueError):
        parameter.to_measurements("P001", "SIM_BP_01")


def test_every_profile_priority_can_be_produced_with_its_registered_unit():
    measurements = {}
    for parameter_type in [*SCALAR_PARAMETERS, BloodPressure]:
        parameter = parameter_type()
        parameter.generate()
        for measurement in parameter.to_measurements("P001", "SIM_01"):
            measurements[measurement.parameter] = measurement
    for profile_type in [DiabetesProfile, HypertensionProfile, AnxietyProfile]:
        for name in profile_type().priority_parameters:
            assert measurements[name].validate()
            assert measurements[name].unit == PARAMETER_DEFINITIONS[name].unit


def test_record_value_rolls_back_invalid_reading_and_its_context():
    parameter = HeartRate()
    parameter.record_value(80)
    previous = (parameter.value, parameter.timestamp, parameter.reading_id)
    with pytest.raises(ValueError):
        parameter.record_value(float("nan"))
    assert (parameter.value, parameter.timestamp, parameter.reading_id) == previous
    parameter.record_value(145)
    assert parameter.value == 145
    assert parameter.reading_id != previous[2]


def test_scalar_parameter_rejects_a_different_parameter_name():
    parameter = HeartRate()
    parameter.record_value(80)
    with pytest.raises(ValueError):
        parameter.record_value({"spo2": 98})
    assert parameter.value == 80
