import math
import re
import threading

import paho.mqtt.client as mqtt

from src.domain.measurement import Measurement


class MQTTPublisher:
    """Publish QoS 1 measurements and wait for the broker's acknowledgement."""

    def __init__(
        self, broker: str = "localhost", port: int = 1883,
        topic: str = "health/{patient_id}/vitals", timeout: float = 5.0, *, security=None,
    ):
        if not isinstance(broker, str) or not broker.strip():
            raise ValueError("broker must be a non-empty host")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if not isinstance(topic, str) or not topic or any(c in topic for c in ("+", "#", "\x00")):
            raise ValueError("Publish topics must be non-empty and cannot contain wildcards")
        if "{" in topic.replace("{patient_id}", "") or "}" in topic.replace("{patient_id}", ""):
            raise ValueError("Only the {patient_id} topic placeholder is supported")
        self.broker = broker
        self.port = port
        self.topic = topic
        self.timeout = timeout
        self._connected = threading.Event()
        self._connect_result = threading.Event()
        self._connection_error = None
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.connect_timeout = timeout
        if security:
            security.configure(self.client)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self._connection_error = str(reason_code)
            self._connected.clear()
        else:
            self._connection_error = None
            self._connected.set()
        self._connect_result.set()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._connected.clear()

    def connect(self) -> None:
        if self._connected.is_set():
            return
        self._connect_result.clear()
        self._connection_error = None
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
            if not self._connect_result.wait(self.timeout):
                raise TimeoutError(f"No MQTT CONNACK from {self.broker}:{self.port}")
            if not self._connected.is_set():
                raise ConnectionError(f"MQTT connection refused: {self._connection_error}")
        except Exception:
            self.disconnect()
            raise

    def publish(self, measurement: Measurement) -> int:
        if not self._connected.is_set():
            raise ConnectionError("Connect to the MQTT broker before publishing")
        if not isinstance(measurement, Measurement):
            raise TypeError("measurement must be a Measurement")
        if not isinstance(measurement.patient_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", measurement.patient_id):
            raise ValueError("patient_id must be safe as a single MQTT topic segment")
        topic = self.topic.replace("{patient_id}", measurement.patient_id)
        info = self.client.publish(topic, measurement.to_json(), qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish failed: {mqtt.error_string(info.rc)}")
        info.wait_for_publish(timeout=self.timeout)
        if not info.is_published():
            raise TimeoutError(f"No MQTT PUBACK for message {info.mid}")
        return info.mid

    def disconnect(self) -> None:
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()
            self._connected.clear()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()
