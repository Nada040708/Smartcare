import json
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.measurement import Measurement
from src.domain.ieee11073_metadata import IEEE11073Metadata
from src.processing import DataValidator, AnomalyDetector
from src.repositories import MeasurementRepository
from src.dashboard import Dashboard
from src.repositories import AlertRepository


def make_measurement(**overrides):
    fields = dict(
        measurement_id="M001", patient_id="P001", device_id="SIM_HR_01",
        parameter="heart_rate", value=84.0, unit="bpm", quality="valid",
        timestamp=datetime(2026, 10, 8, 16, tzinfo=timezone(timedelta(hours=1))),
    )
    fields.update(overrides)
    return Measurement(**fields)


def test_structured_json_contains_context_and_preserves_time_zone():
    measurement = make_measurement()
    data = json.loads(measurement.to_json())

    assert data["patient_id"] == "P001"
    assert data["device_id"] == "SIM_HR_01"
    assert data["parameter"] == "heart_rate"
    assert data["value"] == 84.0
    assert data["unit"] == "bpm"
    assert data["timestamp"] == "2026-10-08T16:00:00+01:00"
    assert "values" not in data
    assert data["reading_id"] == "M001"
    assert data["ieee11073_metadata"]["timestamp"] == data["timestamp"]
    assert data["ieee11073_metadata"]["quality"] == data["quality"]


@pytest.mark.parametrize("overrides", [
    {"measurement_id": " "}, {"patient_id": ""}, {"patient_id": 42},
    {"device_id": None}, {"device_id": ""}, {"reading_id": ""},
    {"parameter": "unknown"}, {"parameter": []},
    {"unit": "mg/dL"}, {"unit": None}, {"quality": "unknown"},
    {"quality": []}, {"device_type": ""},
    {"timestamp": datetime(2026, 10, 8)}, {"timestamp": "2026-10-08"},
    {"value": None}, {"value": True}, {"value": "84"},
    {"value": float("nan")}, {"value": float("inf")},
    {"value": float("-inf")}, {"value": 10 ** 400},
])
def test_invalid_structured_readings_cannot_be_serialized(overrides):
    measurement = make_measurement(**overrides)
    assert measurement.validate() is False
    with pytest.raises(ValueError):
        measurement.to_json()


def test_default_timestamp_is_aware_utc():
    measurement = make_measurement(timestamp=None)
    assert measurement.timestamp.utcoffset() == timedelta(0)


def test_abnormal_values_are_preserved_for_the_rule_engine():
    measurement = make_measurement(value=145.0, timestamp=None)
    assert measurement.validate()
    assert DataValidator().validate(measurement)
    assert AnomalyDetector().detect(measurement)[0]["type"] == "high_heart_rate"


def test_new_measurements_remain_readable_by_existing_repository_and_dashboard():
    measurement = make_measurement()
    repository = MeasurementRepository()
    repository.save(measurement)
    dashboard = Dashboard(repository, AlertRepository())
    assert repository.getByPatient("P001") == [measurement]
    assert dashboard.displayGraphs()["heart_rate"] == [84.0]


def test_legacy_batch_is_copied_and_keeps_its_wire_format():
    values = {"heart_rate": 84.0, "spo2": 98.0}
    measurement = Measurement("M001", "P001", values)
    values.clear()
    data = json.loads(measurement.to_json())
    assert data["values"] == {"heart_rate": 84.0, "spo2": 98.0}
    assert "parameter" not in data
    assert "ieee11073_metadata" not in data
    assert measurement.ieee11073_metadata is None


def test_ambiguous_legacy_and_scalar_inputs_are_rejected():
    with pytest.raises(ValueError):
        make_measurement(values={"heart_rate": 50})


@pytest.mark.parametrize("values", [{}, [], {"heart_rate": True}, {"heart_rate": float("nan")}])
def test_legacy_invalid_values_are_rejected(values):
    measurement = Measurement("M001", "P001", values)
    assert not measurement.validate()


@pytest.mark.parametrize("value, expected", [(0, True), (1, True), (-0.1, False), (1.1, False)])
def test_activity_uses_a_local_normalized_index(value, expected):
    assert make_measurement(parameter="activity", unit="1", value=value).validate() is expected


def test_verified_spo2_mapping_and_metadata_consistency():
    measurement = make_measurement(parameter="spo2", value=98.0, unit="%")
    metadata = measurement.ieee11073_metadata
    assert isinstance(metadata, IEEE11073Metadata)
    assert metadata.metric_code == "150456"
    assert metadata.metric_refid == "MDC_PULS_OXIM_SAT_O2"
    assert metadata.unit_code == "262688"
    assert metadata.mapping_status == "mapped"
    measurement.quality = "questionable"
    data = json.loads(measurement.to_json())
    assert data["ieee11073_metadata"]["quality"] == "questionable"


@pytest.mark.parametrize("parameter, unit", [
    ("heart_rate", "bpm"), ("temperature", "°C"), ("glucose", "mg/dL"),
    ("hrv", "ms"), ("respiratory_rate", "breaths/min"), ("activity", "1"),
])
def test_unverified_mappings_have_no_invented_codes(parameter, unit):
    metadata = make_measurement(parameter=parameter, unit=unit, value=1).ieee11073_metadata
    assert metadata.mapping_status == "unmapped"
    assert metadata.metric_code is None
    assert metadata.unit_code is None
