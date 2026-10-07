import json

import paho.mqtt.client as mqtt

from src.domain.measurement import Measurement


class MQTTPublisher:
    """
    Publishes physiological measurements through MQTT.
    """

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic: str = "health",
    ):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )

    def connect(self) -> None:
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish(self, measurement: Measurement) -> None:
        message = measurement.to_json()

        self.client.publish(
            self.topic,
            message,
            qos=1,
        )

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()