"""Verify Python → Mosquitto → Node-RED → MQTT receipt with fresh measurements."""

import argparse
import json
import threading
import time

import paho.mqtt.client as mqtt

from src.communication import MQTTPublisher
from src.domain import Patient
from src.domain.parameters import HeartRate, BloodPressure
from src.simulation import SensorSimulator
from src.simulation.strategies import NormalStrategy


def build_measurements():
    readings = []
    for patient_id, heart_rate in (("P001", 84), ("P002", 75)):
        patient = Patient(patient_id, "Patient fictif")
        patient.add_parameter(HeartRate())
        strategies = {"heart_rate": NormalStrategy(heart_rate, heart_rate)}
        if patient_id == "P001":
            patient.add_parameter(BloodPressure())
            strategies.update(systolic_bp=NormalStrategy(120, 120), diastolic_bp=NormalStrategy(80, 80))
        simulator = SensorSimulator(patient, strategies=strategies)
        simulator.start()
        try:
            readings.extend(simulator.read())
        finally:
            simulator.stop()
    return readings


def verify_pipeline(broker="localhost", port=1883, timeout=20.0, measurements=None):
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    measurements = build_measurements() if measurements is None else list(measurements)
    if not measurements or len({m.measurement_id for m in measurements}) != len(measurements):
        raise ValueError("Provide non-empty measurements with distinct identifiers")
    expected = {m.measurement_id: m.to_dict() for m in measurements}
    received = {}
    subscribed = threading.Event()
    completed = threading.Event()
    errors = []
    subscriber = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    subscriber.connect_timeout = min(timeout, 5)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            errors.append(f"MQTT connection refused: {reason_code}")
            subscribed.set()
        else:
            client.subscribe("health/+/received", qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            errors.append("MQTT receipt subscription rejected")
        subscribed.set()

    def on_message(client, userdata, message):
        try:
            payload = json.loads(message.payload)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(payload, dict):
            return
        measurement_id = payload.get("measurement_id")
        if not isinstance(measurement_id, str) or measurement_id not in expected:
            return
        wanted = expected[measurement_id]
        if message.topic != f"health/{wanted['patient_id']}/received" or payload != wanted:
            errors.append(f"Node-RED returned a modified or misrouted reading: {measurement_id}")
            completed.set()
            return
        received[measurement_id] = payload
        if len(received) == len(expected):
            completed.set()

    subscriber.on_connect = on_connect
    subscriber.on_subscribe = on_subscribe
    subscriber.on_message = on_message
    try:
        subscriber.connect(broker, port)
        subscriber.loop_start()
        if not subscribed.wait(timeout):
            raise TimeoutError("No MQTT SUBACK for receipt subscription")
        if errors:
            raise ConnectionError(errors[0])
        with MQTTPublisher(broker=broker, port=port, timeout=min(timeout, 5)) as publisher:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not completed.is_set():
                # Node-RED may still be subscribing when its HTTP editor is ready.
                # Resend the same IDs; the receipt check counts each reading once.
                for measurement in measurements:
                    publisher.publish(measurement)
                completed.wait(min(0.5, max(0, deadline - time.monotonic())))
        if errors:
            raise AssertionError(errors[0])
        if len(received) != len(expected):
            raise TimeoutError(f"Node-RED receipts missing: {len(received)}/{len(expected)}. Check the flow and broker settings.")
        return list(received.values())
    finally:
        subscriber.disconnect()
        subscriber.loop_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    try:
        readings = verify_pipeline(args.broker, args.port, args.timeout)
    except (OSError, ValueError, RuntimeError, AssertionError) as error:
        parser.exit(1, f"Échec du test MQTT / Node-RED : {error}\n")
    for reading in readings:
        print(f"Node-RED reçu : {reading['patient_id']} | {reading['parameter']} = {reading['value']} {reading['unit']}")
    print(f"OK : {len(readings)} mesures, 2 patients, trajet Python → Mosquitto → Node-RED vérifié.")


if __name__ == "__main__":
    main()
