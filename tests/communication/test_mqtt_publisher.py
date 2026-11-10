import pytest

from examples.step4_mqtt import verify_pipeline


@pytest.mark.mqtt_integration
def test_python_mosquitto_node_red_round_trip():
    readings = verify_pipeline()
    assert len(readings) == 4
    assert {m["patient_id"] for m in readings} == {"P001", "P002"}
    pressure = [m for m in readings if m["parameter"] in {"systolic_bp", "diastolic_bp"}]
    assert len(pressure) == 2
    assert pressure[0]["reading_id"] == pressure[1]["reading_id"]
    assert pressure[0]["timestamp"] == pressure[1]["timestamp"]
