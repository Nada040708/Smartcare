import argparse
import time

from src.domain import Patient, DiabetesProfile, HypertensionProfile
from src.domain.consent import Consent
from src.domain.parameters import HeartRate, SpO2, Temperature, BloodPressure, Glucose, Activity
from src.simulation import SensorSimulator
from src.simulation.strategies import NormalStrategy, ProgressiveStrategy
from src.processing import DataValidator, AnomalyDetector, AlertEngine, MonitoringStateManager
from src.repositories import MeasurementRepository, AlertRepository
from src.dashboard import Dashboard


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smartcare — démonstration du prototype")
    parser.add_argument("--no-mqtt", action="store_true", help="Exécuter sans broker MQTT")
    parser.add_argument("--cycles", type=int, default=None, help="Nombre de cycles (défaut : continu)")
    parser.add_argument("--interval", type=float, default=2, help="Intervalle entre cycles en secondes")
    parser.add_argument("--mqtt-host", default="localhost", help="Adresse du broker MQTT")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="Port du broker MQTT")
    parser.add_argument("--storage", choices=['postgres', 'memory'], default='postgres', help="Stockage (défaut : PostgreSQL)")
    parser.add_argument("--db-schema", default='smartcare', help="Schéma PostgreSQL utilisé")
    args = parser.parse_args(argv)
    if args.cycles is not None and args.cycles <= 0:
        parser.error("--cycles doit être positif")

    patient = Patient("P001", "Patient 1", profiles=[DiabetesProfile(), HypertensionProfile()], consent=Consent('P001',True))
    for parameter in [HeartRate(), SpO2(), Temperature(), BloodPressure(), Glucose(), Activity()]:
        patient.add_parameter(parameter)
    try:
        simulator = SensorSimulator(patient, interval=args.interval, strategies={
            "heart_rate": NormalStrategy(60, 100),
            "spo2": NormalStrategy(95, 100),
            "temperature": ProgressiveStrategy(step=0.2),
        })
    except ValueError as error:
        parser.error(str(error))

    validator = DataValidator()
    detector = AnomalyDetector(validator=validator)
    alert_engine = AlertEngine()
    state_manager = MonitoringStateManager()
    measurement_repository = MeasurementRepository()
    alert_repository = AlertRepository()
    store = None
    persistent = None
    if args.storage == 'postgres':
        import psycopg
        from src.repositories.postgres_store import PostgresStore
        from src.processing.persistent_monitoring import PersistentMonitoring
        try:
            store = PostgresStore(schema=args.db_schema)
            persistent = PersistentMonitoring(store, detector=detector)
        except (psycopg.Error, ValueError, RuntimeError) as error:
            if store is not None:
                store.close()
            parser.error(f"Stockage PostgreSQL indisponible ({type(error).__name__}). Vérifier Docker et la configuration .env.")
        measurement_repository = persistent.measurements
        alert_repository = persistent.alerts
        alert_engine = persistent.engine
        state_manager = persistent.states
    dashboard = Dashboard(measurement_repository, alert_repository, state_manager)
    publisher = None
    connected = False
    if not args.no_mqtt:
        from src.communication import MQTTPublisher
        publisher = MQTTPublisher(broker=args.mqtt_host, port=args.mqtt_port)

    simulator.start()
    try:
        if publisher is not None:
            publisher.connect()
            connected = True
        print("=== SMARTCARE MONITORING ===")
        print(f"Profiles: {', '.join(profile.name for profile in patient.profiles)}")
        cycle = 0
        while simulator.running and (args.cycles is None or cycle < args.cycles):
            measurements = simulator.read()
            accepted = []
            for measurement in measurements:
                print(f"{measurement.patient_id} | {measurement.parameter}: {measurement.value} {measurement.unit}")
                validation = validator.validate_payload(measurement.to_dict())
                if not validation.accepted:
                    print("Rejected measurement:", validation.to_dict()["errors"])
                    continue
                if publisher is not None:
                    publisher.publish(measurement)
                if persistent is None:
                    measurement_repository.save(measurement)
                accepted.append(measurement)

            # Evaluate the validated scalar cycle using this patient's profiles.
            if persistent is not None:
                persistent.process(accepted, patient)
            else:
                evaluation = detector.evaluate_batch(accepted, patient)
                for alert in alert_engine.process(evaluation):
                    alert_repository.save(alert)
                state_manager.evaluate_state(evaluation, alert_engine.get_active(patient.patient_id))
            print(dashboard.displayStatus())
            dashboard.displayAlerts()
            cycle += 1
            if args.cycles is None or cycle < args.cycles:
                time.sleep(simulator.interval)
    except KeyboardInterrupt:
        print("Stopping monitoring...")
    finally:
        simulator.stop()
        try:
            if connected:
                publisher.disconnect()
        finally:
            if store is not None:
                store.close()
        print("Monitoring stopped.")


if __name__ == "__main__":
    main()
