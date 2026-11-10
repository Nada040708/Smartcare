"""Profile-rule demonstration, with a virtual clock or the real MQTT pipeline."""
import argparse
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.domain import Patient, Measurement, DiabetesProfile, HypertensionProfile, AnxietyProfile
from src.domain.parameters import Glucose, BloodPressure, HeartRate, HRV, RespiratoryRate, Activity
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.processing import AnomalyDetector, DataValidator, AlertEngine
from src.simulation import SensorSimulator
from src.simulation.strategies import NormalStrategy


def show(label, anomalies):
    print(f'\n{label}')
    if not anomalies:
        print('Aucune règle déclenchée (cela ne constitue pas un diagnostic).')
    for anomaly in anomalies:
        print(f"{anomaly['patient_id']} | {anomaly['rule_id']} | {anomaly['severity']} | profils={','.join(anomaly['profile_ids'])}")
        print(anomaly['message'])


def virtual_demo():
    instant = datetime.now(timezone.utc)
    detector = AnomalyDetector(validator=DataValidator(now=lambda:instant))
    diabetic = Patient('P001','Patient 1',profiles=[DiabetesProfile(),HypertensionProfile()])
    anxiety = Patient('P002','Patient 2',profiles=[AnxietyProfile()])
    def reading(patient,parameter,value):
        return Measurement(str(uuid4()),patient.patient_id,device_id=f'SIM_{patient.patient_id}',
                           parameter=parameter,value=value,unit=PARAMETER_DEFINITIONS[parameter].unit,
                           timestamp=instant,quality='valid',device_type='simulator')
    show('Même glycémie, profil diabète',detector.detect(reading(diabetic,'glucose',220),diabetic))
    show('Même glycémie, profil anxiété',detector.detect(reading(anxiety,'glucose',220),anxiety))
    for value in [110,120,130]:
        show(f'Tendance systolique P001 : {value} mmHg',detector.detect(reading(diabetic,'systolic_bp',value),diabetic))
        instant += timedelta(seconds=5)
    active=[reading(anxiety,p,v) for p,v in [('heart_rate',120),('hrv',20),('respiratory_rate',25),('activity',0.8)]]
    show('Combinaison avec activité élevée',detector.detect_batch(active,anxiety))
    instant += timedelta(seconds=1)
    resting=reading(anxiety,'activity',0.1)
    show('Même combinaison, contexte de repos',detector.detect(resting,anxiety))
    show('Doublon MQTT de la même mesure',detector.detect(resting,anxiety))


def verify_mqtt_rules(broker='localhost',port=1883):
    from examples.step4_mqtt import verify_pipeline
    patients={
        'P001':Patient('P001','Patient 1',profiles=[DiabetesProfile(),HypertensionProfile()]),
        'P002':Patient('P002','Patient 2',profiles=[AnxietyProfile()]),
    }
    definitions={
        'P001':([Glucose(),BloodPressure()],{'glucose':220,'systolic_bp':150,'diastolic_bp':95}),
        'P002':([HeartRate(),HRV(),RespiratoryRate(),Activity()],{'heart_rate':120,'hrv':20,'respiratory_rate':25,'activity':0.1}),
    }
    measurements=[]
    for patient_id,(parameters,values) in definitions.items():
        patient=patients[patient_id]
        for parameter in parameters:
            patient.add_parameter(parameter)
        simulator=SensorSimulator(patient,strategies={name:NormalStrategy(value,value) for name,value in values.items()})
        simulator.start()
        try:
            measurements.extend(simulator.read())
        finally:
            simulator.stop()
    receipts=verify_pipeline(broker=broker,port=port,measurements=measurements)
    detector=AnomalyDetector()
    anomalies=[]
    for payload in receipts:
        anomalies.extend(detector.detect_payload(payload,patients[payload['patient_id']]))
    expected={'diabetes_glucose_high','hypertension_systolic_high','hypertension_diastolic_high','high_heart_rate','anxiety_rest_pattern'}
    if {a['rule_id'] for a in anomalies} != expected or len(anomalies) != 5:
        raise AssertionError(f"Unexpected rules after MQTT: {[a['rule_id'] for a in anomalies]}")
    alerts=[]
    engine=AlertEngine()
    for patient_id in patients:
        alerts.extend(engine.evaluate(patient_id,[a for a in anomalies if a['patient_id']==patient_id]))
    return anomalies,alerts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mqtt',action='store_true',help='Use real Mosquitto/Node-RED receipts before evaluating rules')
    parser.add_argument('--broker',default='localhost')
    parser.add_argument('--port',type=int,default=1883)
    args=parser.parse_args()
    if args.mqtt:
        try:
            anomalies,alerts=verify_mqtt_rules(args.broker,args.port)
        except (OSError,ValueError,RuntimeError,AssertionError) as error:
            parser.exit(1,f'Échec de la démonstration : {error}\n')
        show('Mesures reçues de Node-RED → règles Python',anomalies)
        print(f'OK : 7 mesures, 2 patients, {len(anomalies)} règles déclenchées, {len(alerts)} alertes de démonstration.')
    else:
        virtual_demo()


if __name__ == '__main__':
    main()
