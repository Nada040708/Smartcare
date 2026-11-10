"""Send valid and deliberately invalid raw messages through the real Node-RED flow."""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import threading
import time
from uuid import uuid4

import paho.mqtt.client as mqtt

from src.domain import Measurement


def build_cases():
    base = Measurement(str(uuid4()), 'P001', device_id='SIM_VALIDATION', parameter='heart_rate', value=145,
                       unit='bpm', quality='valid').to_dict()
    cases = []
    def add(name, change=None, code=None):
        payload = deepcopy(base)
        payload['measurement_id'] = str(uuid4())
        payload['reading_id'] = payload['measurement_id']
        if change:
            change(payload)
        cases.append({'name':name, 'payload':payload, 'code':code})
    def timestamp(seconds):
        def change(payload):
            value = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
            payload['timestamp'] = value
            payload['ieee11073_metadata']['timestamp'] = value
        return change
    def quality(payload):
        payload['quality'] = 'questionable'
        payload['ieee11073_metadata']['quality'] = 'questionable'
    add('145 bpm : transmis au futur moteur de règles')
    add('Unité incorrecte', lambda p:p.update(unit='mg/dL'), 'unit_mismatch')
    add('Valeur hors limite technique', lambda p:p.update(value=500), 'out_of_range')
    add('Mesure ancienne', timestamp(-180), 'stale_timestamp')
    add('Mesure future', timestamp(60), 'future_timestamp')
    add('Qualité insuffisante', quality, 'invalid_quality')
    add('Métadonnées contradictoires', lambda p:p['ieee11073_metadata'].update(metric_code='123'), 'metadata_mismatch')
    add('Paramètre inconnu', lambda p:p.update(parameter='unknown'), 'unknown_parameter')
    return cases


def verify_validation(broker='localhost', port=1883, timeout=20):
    cases = build_cases()
    expected = {case['payload']['measurement_id']:case for case in cases}
    received = {}
    ready = threading.Event()
    done = threading.Event()
    errors = []
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect_timeout = 5

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            errors.append(str(reason_code)); ready.set()
        else:
            client.subscribe([('health/P001/received',1),('health/P001/rejected',1)])

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            errors.append('Subscription rejected')
        ready.set()

    def on_message(client, userdata, message):
        try:
            payload = json.loads(message.payload)
            key = payload.get('measurement_id') if isinstance(payload,dict) else None
            if not isinstance(key,str) or key not in expected:
                return
            case = expected[key]
            should_reject = case['code'] is not None
            wanted_topic = 'health/P001/rejected' if should_reject else 'health/P001/received'
            if message.topic != wanted_topic:
                raise AssertionError(f"Unexpected route for {case['name']}")
            if should_reject:
                if payload.get('accepted') is not False or case['code'] not in {e['code'] for e in payload.get('errors',[])}:
                    raise AssertionError(f"Wrong rejection reason for {case['name']}")
            elif payload != case['payload']:
                raise AssertionError('Accepted measurement was modified')
            received[key] = case
            if len(received) == len(expected):
                done.set()
        except (ValueError, KeyError, TypeError, AssertionError) as error:
            errors.append(str(error)); done.set()

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    try:
        client.connect(broker,port)
        client.loop_start()
        if not ready.wait(timeout):
            raise TimeoutError('Missing subscription acknowledgement')
        if errors:
            raise RuntimeError(errors[0])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not done.is_set():
            for case in cases:
                # Deliberately bypass MQTTPublisher's local validation: test incoming untrusted data.
                info = client.publish('health/P001/vitals', json.dumps(case['payload']), qos=1, retain=False)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise ConnectionError(mqtt.error_string(info.rc))
                info.wait_for_publish(timeout=5)
                if not info.is_published():
                    raise TimeoutError('Missing publication acknowledgement')
            done.wait(0.5)
        if errors:
            raise AssertionError(errors[0])
        if len(received) != len(expected):
            raise TimeoutError(f"Validation results missing: {len(received)}/{len(expected)}")
        return list(received.values())
    finally:
        client.disconnect()
        client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker',default='localhost')
    parser.add_argument('--port',type=int,default=1883)
    args = parser.parse_args()
    try:
        cases = verify_validation(args.broker,args.port)
    except (OSError,ValueError,RuntimeError,AssertionError) as error:
        parser.exit(1,f'Échec de validation : {error}\n')
    for case in cases:
        print(('ACCEPTÉ' if case['code'] is None else 'REJETÉ '+case['code']) + ' — ' + case['name'])
    print(f'OK : {len(cases)} décisions de validation vérifiées via MQTT et Node-RED.')


if __name__ == '__main__':
    main()
