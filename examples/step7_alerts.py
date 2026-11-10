"""Demonstrate patient states and alert episodes, locally or through Node-RED."""
import argparse
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.domain import Patient, DiabetesProfile, Measurement
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.processing import AnomalyDetector, DataValidator, AlertEngine, MonitoringStateManager
from src.repositories import AlertRepository


def run_demo(mqtt=False, broker='localhost', port=1883):
    instant = datetime.now(timezone.utc)
    patients = {pid: Patient(pid, f'Patient fictif {pid}', profiles=[DiabetesProfile()])
                for pid in ('P001', 'P002')}
    detector = AnomalyDetector(DataValidator(now=lambda: instant) if not mqtt else None)
    engine = AlertEngine(recovery_confirmations=2)
    states = MonitoringStateManager()
    repository = AlertRepository()
    normal = {'heart_rate': 80, 'spo2': 98, 'temperature': 37, 'glucose': 110}
    abnormal = dict(normal, heart_rate=140, spo2=90, glucose=220)
    snapshots = []
    previous_measurements = []
    received_count = 0
    scenarios = [
        ('Normal', normal), ('Anomalie brutale', abnormal), ('Anomalie persistante', abnormal),
        ('Déconnexion signalée', None), ('Retour : confirmation 1/2', normal),
        ('Doublon du même cycle', 'duplicate'), ('Retour : confirmation 2/2', normal),
        ('Nouvel épisode', abnormal),
    ]
    for label, values in scenarios:
        instant = datetime.now(timezone.utc) if mqtt else instant + timedelta(seconds=1)
        if values == 'duplicate':
            measurements = previous_measurements
        elif values is None:
            measurements = []
        else:
            measurements = [Measurement(
                str(uuid4()), pid, device_id=f'SIM_{pid}', parameter=parameter,
                value=value, unit=PARAMETER_DEFINITIONS[parameter].unit,
                timestamp=instant, quality='valid', device_type='simulator',
            ) for pid in patients for parameter, value in (values if pid == 'P001' else normal).items()]
            previous_measurements = measurements
        if mqtt and measurements:
            from examples.step4_mqtt import verify_pipeline
            payloads = verify_pipeline(broker=broker, port=port, measurements=measurements)
            received_count += len(payloads)
        else:
            payloads = [m.to_dict() for m in measurements]
        for payload in payloads:
            report = detector.evaluate_payload(payload, patients[payload['patient_id']])
            for alert in engine.process(report):
                repository.save(alert)
            states.evaluate_state(report, engine.get_active())
        if values is None:
            report = detector.evaluate_batch([], patients['P001'])
            for alert in engine.process(report, connected=False):
                repository.save(alert)
            states.evaluate_state(report, engine.get_active(), connected=False)
        snapshot = {'label': label, 'state': states.get_state('P001').value,
                    'active': len(engine.get_active('P001')),
                    'history': len(repository.getHistory()),
                    'occurrences': {a.rule_id: a.occurrences for a in engine.get_active('P001')}}
        snapshots.append(snapshot)
        print(f"{label:30} | P001={snapshot['state']:12} | alertes actives={snapshot['active']} | épisodes={snapshot['history']}")
        if states.get_state('P002').value != 'NORMAL' or engine.get_active('P002'):
            raise AssertionError('P002 must remain isolated and NORMAL')
    expected_states = ['NORMAL', 'CRITICAL', 'CRITICAL', 'DISCONNECTED', 'CRITICAL', 'CRITICAL', 'NORMAL', 'CRITICAL']
    if [s['state'] for s in snapshots] != expected_states:
        raise AssertionError(f'Unexpected state transitions: {snapshots}')
    if [s['active'] for s in snapshots] != [0, 4, 4, 4, 4, 4, 0, 4]:
        raise AssertionError(f'Unexpected active alert counts: {snapshots}')
    history = repository.getHistory()
    if len(history) != 8 or any(a.occurrences != 1 for a in history[4:]):
        raise AssertionError('Expected four resolved episodes and four new episodes')
    if snapshots[4]['occurrences'] != snapshots[5]['occurrences']:
        raise AssertionError('Duplicate messages must not increment occurrences')
    print('OK : épisodes dédupliqués, résolution confirmée, récidive distincte ; P002 reste NORMAL.')
    if mqtt:
        print(f'OK MQTT : {received_count} reçus Node-RED validés (dont 8 doublons intentionnels).')
    return snapshots, history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mqtt', action='store_true')
    parser.add_argument('--broker', default='localhost')
    parser.add_argument('--port', type=int, default=1883)
    args = parser.parse_args()
    try:
        run_demo(args.mqtt, args.broker, args.port)
    except (OSError, ValueError, RuntimeError, AssertionError) as error:
        parser.exit(1, f'Échec de la démonstration : {error}\n')


if __name__ == '__main__':
    main()
