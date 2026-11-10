"""Persist data and resume an alert episode across separate Python sessions."""
import argparse
from datetime import datetime, timezone
from uuid import uuid4

import psycopg

from src.domain import Patient, DiabetesProfile, Measurement
from src.processing import AnomalyDetector
from src.processing.persistent_monitoring import PersistentMonitoring
from src.repositories.postgres_store import PostgresStore
from src.repositories.postgres_repositories import (PostgresMeasurementRepository,
                                                    PostgresAlertRepository, PostgresEventRepository)


def reading(patient_id, value):
    return Measurement(str(uuid4()), patient_id, device_id=f'SIM_{patient_id}',
                       parameter='glucose', value=value, unit='mg/dL', quality='valid',
                       timestamp=datetime.now(timezone.utc), device_type='simulator')


def seed(schema, mqtt=False):
    with PostgresStore(schema=schema) as store:
        if PostgresMeasurementRepository(store).count() or PostgresAlertRepository(store).count():
            raise ValueError('Le schéma contient déjà des données : choisir un nouveau --schema pour seed.')
        session = PersistentMonitoring(store, detector=AnomalyDetector(common_rules=[]))
        from src.domain.consent import Consent
        patients = {pid: Patient(pid, 'Patient fictif', profiles=[DiabetesProfile()],consent=Consent(pid,True)) for pid in ('P001', 'P002')}
        measures = [reading('P001', 220), reading('P002', 110)]
        if mqtt:
            from examples.step4_mqtt import verify_pipeline
            for payload in verify_pipeline(measurements=measures):
                session.process_payload(payload, patients[payload['patient_id']])
            print('Deux mesures reçues de Node-RED et stockées dans PostgreSQL.')
        else:
            for measure in measures:
                session.process([measure], patients[measure.patient_id])
        session.process([reading('P001', 110)], patients['P001'])
        alert = session.alerts.getActive()[0]
        if session.measurements.count() != 3 or alert.recovery_count != 1:
            raise AssertionError('Expected three measurements and one pending recovery confirmation')
        print(f'Session 1 : 3 mesures, 1 alerte ACTIVE, confirmation 1/2 ; épisode {alert.alert_id}.')


def resume(schema):
    with PostgresStore(schema=schema) as store:
        if PostgresMeasurementRepository(store).count() != 3 or len(PostgresAlertRepository(store).getActive()) != 1:
            raise ValueError('Exécuter seed dans un schéma neuf avant resume.')
        session = PersistentMonitoring(store, detector=AnomalyDetector(common_rules=[]))
        from src.domain.consent import Consent
        patient = Patient('P001', 'Patient fictif', profiles=[DiabetesProfile()],consent=Consent('P001',True))
        alert = session.alerts.getActive()[0]
        alert_id = alert.alert_id
        if alert.recovery_count != 0:
            raise AssertionError('Recovery confirmation must restart after reopening')
        print(f'Session 2 : même épisode {alert_id}, confirmations remises à zéro.')
        replay = session.measurements.getByPatient('P001')[0]
        session.process([replay], patient)
        if session.measurements.count() != 3 or session.alerts.getActive()[0].occurrences != 1:
            raise AssertionError('Historical replay must not create a row or occurrence')
        session.process([reading('P001', 230)], patient)
        if session.alerts.getActive()[0].alert_id != alert_id:
            raise AssertionError('Persistent anomaly must reuse the restored episode')
        session.process([reading('P001', 110)], patient)
        if not session.alerts.getActive():
            raise AssertionError('One confirmation is not enough')
        session.process([reading('P001', 112)], patient)
        if session.alerts.getActive() or session.alerts.count() != 1:
            raise AssertionError('Expected one resolved episode')
        print('Doublon ignoré ; même alerte actualisée puis résolue après deux nouvelles confirmations.')


def inspect(schema):
    with PostgresStore(schema=schema) as store:
        measurements = PostgresMeasurementRepository(store)
        alerts = PostgresAlertRepository(store)
        events = PostgresEventRepository(store)
        summary = dict(measurements=measurements.count(), alerts=alerts.count(),
                       active_alerts=alerts.count(active=True), events=events.count())
        print(f'Schéma {schema} : {summary}')
        for alert in alerts.getHistory():
            print(f'{alert.alert_id} | {alert.patient_id} | {alert.status} | occurrences={alert.occurrences} | {alert.resolution_reason}')
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema', help='Schéma de démonstration, distinct de smartcare')
    parser.add_argument('--phase', choices=['all', 'seed', 'resume', 'inspect'], default='all')
    parser.add_argument('--mqtt', action='store_true', help='Passer les deux premières mesures par Mosquitto/Node-RED')
    args = parser.parse_args()
    if args.phase in {'resume', 'inspect'} and not args.schema:
        parser.error('--schema est requis pour retrouver les données existantes')
    schema = args.schema or 'smartcare_demo_' + uuid4().hex[:12]
    if schema == 'smartcare':
        parser.error('Utiliser un schéma de démonstration distinct de smartcare')
    print(f'Schéma conservé pour inspection : {schema}')
    try:
        if args.phase in {'all', 'seed'}:
            seed(schema, args.mqtt)
        if args.phase in {'all', 'resume'}:
            resume(schema)
        inspect(schema)
    except psycopg.Error as error:
        parser.exit(1, f'Échec PostgreSQL ({type(error).__name__}) : vérifier Docker et la configuration .env.\n')
    except (ValueError, RuntimeError, OSError, AssertionError) as error:
        parser.exit(1, f'Échec de la démonstration : {error}\n')


if __name__ == '__main__':
    main()
