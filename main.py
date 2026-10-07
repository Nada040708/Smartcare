import time

from src.domain.patient import Patient
from src.domain.parameters import HeartRate, SpO2, Temperature

from src.simulation import SensorSimulator
from src.simulation.strategies import NormalStrategy, ProgressiveStrategy


from src.communication import MQTTPublisher

from src.processing import (
    DataValidator,
    AnomalyDetector,
    AlertEngine,
)

from src.repositories import (
    MeasurementRepository,
    AlertRepository,
)

from src.dashboard import Dashboard


def main():
    # =========================
    # 1. Patient
    # =========================

    patient = Patient(
        patient_id="P001",
        name="Patient 1",
    )

    patient.add_parameter(HeartRate())
    patient.add_parameter(SpO2())
    patient.add_parameter(Temperature())

    # =========================
    # 2. Sensor Simulator
    # =========================

    simulator = SensorSimulator(interval=2)
    strategies = {
    "heart_rate": NormalStrategy(60.0, 100.0),
    "spo2": NormalStrategy(95.0, 100.0),
    "temperature": ProgressiveStrategy(step=1),
    }

    # =========================
    # 3. Components
    # =========================

    publisher = MQTTPublisher(
        broker="localhost",
        port=1883,
        topic="health/P001/vitals",
    )

    validator = DataValidator()
    detector = AnomalyDetector()
    alert_engine = AlertEngine()

    measurement_repository = MeasurementRepository()
    alert_repository = AlertRepository()

    dashboard = Dashboard(
        measurement_repository,
        alert_repository,
    )

    # =========================
    # 4. Start monitoring
    # =========================

    simulator.start()
    publisher.connect()

    print("\n=== SMARTCARE MONITORING ===")
    print("Monitoring started.")
    print("Press Ctrl+C to stop.\n")

    try:
        while simulator.running:

            # Generate a new measurement
            measurement = simulator.generate_measurement(
                patient,
                strategies,
            )

            print("\n=== NEW MEASUREMENT ===")
            print(
                f"Patient: {measurement.patient_id}"
            )
            print(
                f"Heart Rate: "
                f"{measurement.values['heart_rate']} bpm"
            )
            print(
                f"SpO2: "
                f"{measurement.values['spo2']} %"
            )
            print(
                f"Temperature: "
                f"{measurement.values['temperature']} °C"
            )

            # =========================
            # 5. MQTT
            # =========================

            publisher.publish(measurement)

            # =========================
            # 6. Validation
            # =========================

            if not validator.validate(measurement):
                print("Invalid measurement.")
                time.sleep(simulator.interval)
                continue

            # =========================
            # 7. Anomaly Detection
            # =========================

            anomalies = detector.detect(measurement)

            # =========================
            # 8. Alert Engine
            # =========================

            alerts = alert_engine.evaluate(
                patient_id=patient.patient_id,
                anomalies=anomalies,
            )

            # =========================
            # 9. Repositories
            # =========================

            measurement_repository.save(measurement)

            for alert in alerts:
                alert_repository.save(alert)

            # =========================
            # 10. Dashboard
            # =========================

            print("\n=== STATUS ===")

            dashboard.displayMeasurements()
            dashboard.displayAlerts()

            print(
                f"Measurements: "
                f"{dashboard.displayStatus()['measurements_count']}"
            )

            print(
                f"Active alerts: "
                f"{dashboard.displayStatus()['active_alerts_count']}"
            )

            # Wait before next measurement
            time.sleep(simulator.interval)

    except KeyboardInterrupt:
        print("\n\nStopping monitoring...")

    finally:
        simulator.stop()
        publisher.disconnect()

        print("Monitoring stopped.")


if __name__ == "__main__":
    main()