"""Publish a multipatient scenario; the dashboard receiver performs all storage."""
import argparse
import math
import time
from datetime import datetime, timezone
from uuid import uuid4

from src.communication import MQTTPublisher
from src.domain import Measurement
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.web.patients import load_patients, DEFAULT_PATIENTS
from src.communication.tls import TLSService


def cycle_measurements(patients, cycle, scenario='mixed'):
    moment = datetime.now(timezone.utc)
    measurements = []
    # Repeating phases: normal → progressive anomaly → sustained → recovery.
    phase = cycle % 40
    for index, patient in enumerate(patients.values()):
        if not patient.monitoring_enabled:
            continue
        wave = math.sin(cycle / 3 + index)
        values = dict(heart_rate=round(77+5*wave,1), spo2=98, temperature=36.8,
                      systolic_bp=round(120+2*wave,1), diastolic_bp=78,
                      glucose=round(115+5*wave,1), hrv=48, respiratory_rate=16, activity=.1)
        if scenario == 'mixed' and 10 <= phase < 28:
            if index == 0:
                values['glucose'] = round(160 + min(phase-10,8)*9,1)
                values['systolic_bp'] = round(132 + min(phase-10,8)*3,1)
                values['diastolic_bp'] = 94
            elif index == 1:
                values.update(heart_rate=118, hrv=22, respiratory_rate=25, activity=.1)
                if phase >= 20:
                    values['spo2'] = 92
        reading_id = str(uuid4())
        for parameter, value in values.items():
            measurements.append(Measurement(str(uuid4()), patient.patient_id,
                device_id=f'SIM_{patient.patient_id}', parameter=parameter, value=value,
                unit=PARAMETER_DEFINITIONS[parameter].unit, quality='valid', timestamp=moment,
                reading_id=reading_id, device_type='simulator'))
    return measurements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=60)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--scenario', choices=['normal', 'mixed'], default='mixed')
    parser.add_argument('--patients', default=str(DEFAULT_PATIENTS))
    parser.add_argument('--broker', default='localhost')
    parser.add_argument('--port', type=int, default=1883)
    parser.add_argument('--mqtt-config', help='Configuration privée MQTT/TLS (étape 10, port 8883)')
    args = parser.parse_args()
    if args.cycles < 1 or not math.isfinite(args.interval) or args.interval <= 0:
        parser.error('cycles et interval doivent être positifs')
    patients = load_patients(args.patients)
    try:
        security = TLSService.from_file(args.mqtt_config) if args.mqtt_config else None
        with MQTTPublisher(broker=args.broker, port=args.port, security=security) as publisher:
            for cycle in range(args.cycles):
                readings = cycle_measurements(patients, cycle, args.scenario)
                for reading in readings:
                    publisher.publish(reading)
                print(f'Cycle {cycle+1}/{args.cycles} : {len(readings)} mesures publiées.', flush=True)
                if cycle+1 < args.cycles:
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        print('Simulation arrêtée.')


if __name__ == '__main__':
    main()
