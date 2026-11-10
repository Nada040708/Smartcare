import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import paho.mqtt.client as mqtt

from src.communication import MQTTPublisher
from src.domain import Measurement


def measurement(patient_id="P001"):
    return Measurement("M1", patient_id, device_id="SIM_01", parameter="heart_rate", value=84, unit="bpm")


@pytest.fixture
def publisher():
    with patch("src.communication.mqtt_publisher.mqtt.Client") as factory:
        client = factory.return_value
        def connected():
            client.on_connect(client, None, None, SimpleNamespace(is_failure=False), None)
        client.loop_start.side_effect = connected
        publisher = MQTTPublisher(timeout=0.01)
        info = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS, mid=42)
        info.is_published.return_value = True
        client.publish.return_value = info
        yield publisher


def test_publish_routes_each_patient_and_waits_for_broker_ack(publisher):
    publisher.connect()
    assert publisher.publish(measurement("P001")) == 42
    publisher.publish(measurement("P002"))
    calls = publisher.client.publish.call_args_list
    assert calls[0].args[0] == "health/P001/vitals"
    assert calls[1].args[0] == "health/P002/vitals"
    assert json.loads(calls[0].args[1])["value"] == 84
    assert calls[0].kwargs == {"qos": 1, "retain": False}
    publisher.client.publish.return_value.wait_for_publish.assert_called_with(timeout=0.01)
    publisher.disconnect()
    publisher.client.disconnect.assert_called_once()
    publisher.client.loop_stop.assert_called_once()


def test_publish_before_connect_or_after_disconnect_is_rejected(publisher):
    with pytest.raises(ConnectionError):
        publisher.publish(measurement())
    publisher.connect()
    publisher.client.on_disconnect(None, None, None, None, None)
    with pytest.raises(ConnectionError):
        publisher.publish(measurement())


def test_connack_timeout_cleans_up_network_loop(publisher):
    publisher.client.loop_start.side_effect = None
    with pytest.raises(TimeoutError, match="CONNACK"):
        publisher.connect()
    publisher.client.loop_stop.assert_called_once()


def test_connection_rejection_is_reported(publisher):
    publisher.client.loop_start.side_effect = lambda: publisher._on_connect(None, None, None, SimpleNamespace(is_failure=True), None)
    with pytest.raises(ConnectionError, match="refused"):
        publisher.connect()


def test_publish_timeout_is_not_reported_as_success(publisher):
    publisher.connect()
    publisher.client.publish.return_value.is_published.return_value = False
    with pytest.raises(TimeoutError, match="PUBACK"):
        publisher.publish(measurement())


def test_immediate_publish_error_is_reported(publisher):
    publisher.connect()
    publisher.client.publish.return_value.rc = mqtt.MQTT_ERR_NO_CONN
    with pytest.raises(ConnectionError):
        publisher.publish(measurement())


def test_invalid_payload_and_topic_identifiers_are_not_published(publisher):
    publisher.connect()
    with pytest.raises(ValueError):
        publisher.publish(measurement("P/001"))
    invalid = measurement()
    invalid.value = float("nan")
    with pytest.raises(ValueError):
        publisher.publish(invalid)
    publisher.client.publish.assert_not_called()


@pytest.mark.parametrize("config", [
    {"port": 0}, {"port": True}, {"broker": ""}, {"timeout": 0},
    {"topic": "health/+/vitals"}, {"topic": "health/{unknown}"},
])
def test_invalid_configuration_is_rejected(config):
    with pytest.raises(ValueError):
        MQTTPublisher(**config)
