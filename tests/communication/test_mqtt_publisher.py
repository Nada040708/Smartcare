import json
import threading
import time

from src.communication import MQTTPublisher
from src.domain.measurement import Measurement

import paho.mqtt.client as mqtt


def test_mqtt_publisher():

    received_message = {}
    message_received = threading.Event()

    def on_message(client, userdata, message):
        received_message["topic"] = message.topic
        received_message["payload"] = message.payload.decode()
        message_received.set()

    subscriber = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    subscriber.on_message = on_message

    subscriber.connect("localhost", 1883)
    subscriber.subscribe("health/test", qos=1)
    subscriber.loop_start()

    time.sleep(0.5)

    publisher = MQTTPublisher(
        broker="localhost",
        port=1883,
        topic="health/test",
    )

    publisher.connect()

    measurement = Measurement(
        measurement_id="M001",
        patient_id="P001",
        values={
            "heart_rate": 78.0,
            "spo2": 98.0,
            "temperature": 36.7,
        },
    )

    publisher.publish(measurement)

    assert message_received.wait(timeout=3)

    payload = json.loads(received_message["payload"])

    assert received_message["topic"] == "health/test"
    assert payload["measurement_id"] == "M001"
    assert payload["patient_id"] == "P001"
    assert payload["values"]["heart_rate"] == 78.0

    publisher.disconnect()

    subscriber.loop_stop()
    subscriber.disconnect()