"""Demonstrate silence, partial readings and recovery over verified MQTT/TLS."""
import argparse
import math
import time

from examples.step9_live import cycle_measurements
from src.communication import MQTTPublisher
from src.communication.tls import TLSService
from src.processing.connection_monitor import load_connection_policy, DEFAULT_POLICY
from src.web.patients import load_patients, DEFAULT_PATIENTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patient', default='P001')
    parser.add_argument('--patients', default=str(DEFAULT_PATIENTS))
    parser.add_argument('--parameter', default='glucose')
    parser.add_argument('--connection-policy', default=str(DEFAULT_POLICY))
    parser.add_argument('--mqtt-config', default='.secrets/simulator.json')
    parser.add_argument('--broker', default='localhost')
    parser.add_argument('--port', type=int, default=8883)
    parser.add_argument('--interval', type=float, default=1)
    args = parser.parse_args()
    patients = load_patients(args.patients)
    policy = load_connection_policy(args.connection_policy)
    if args.patient not in patients or not patients[args.patient].monitoring_enabled:
        parser.error('Choisir un patient configuré avec surveillance activée.')
    expected = {p for d in policy['devices'] if d['patient_id']==args.patient for p in d['parameters']}
    if args.parameter not in expected:
        parser.error('Le paramètre doit être attendu pour ce patient dans la politique de connexion.')
    if not math.isfinite(args.interval) or not 0 < args.interval < policy['timeout_seconds']/2:
        parser.error('interval doit être positif et inférieur à la moitié du délai de déconnexion.')
    hold = math.ceil((max(policy['timeout_seconds'],policy['startup_grace_seconds'])+3)/args.interval)
    phases = [('normal', 4), ('silence', hold), ('recovery', 4), ('missing', hold), ('recovery', 4)]
    labels = {'normal':'Données normales', 'silence':'Capteur silencieux',
              'missing':f'Paramètre absent : {args.parameter}', 'recovery':'Données complètes rétablies'}
    cycle = 0
    try:
        with MQTTPublisher(broker=args.broker,port=args.port,security=TLSService.from_file(args.mqtt_config)) as publisher:
            for phase, count in phases:
                print(f'{args.patient} — {labels[phase]} ({count} cycles). Les autres patients continuent.',flush=True)
                for _ in range(count):
                    for measurement in cycle_measurements(patients,cycle,scenario='normal'):
                        if measurement.patient_id == args.patient and (phase=='silence' or
                            (phase=='missing' and measurement.parameter==args.parameter)):
                            continue
                        publisher.publish(measurement)
                    cycle += 1
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        print('Scénario arrêté ; les délais de surveillance restent actifs côté serveur.')


if __name__ == '__main__':
    main()
