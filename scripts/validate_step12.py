"""Measure the real local TLS pipeline; write reproducible, non-clinical acceptance KPIs."""
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import hashlib
import json
import math
import platform
import secrets
import ssl
import sys
import threading
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import httpx
from psycopg import sql
import uvicorn
from examples.step9_live import cycle_measurements
from src.communication import MQTTPublisher
from src.communication.tls import TLSService
from src.domain import Consent
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.repositories.postgres_store import PostgresStore
from src.repositories.postgres_repositories import PostgresMeasurementRepository
from src.security.authentication import AuthenticationService
from src.web.app import create_app
from src.web.patients import load_patients


def wait_for(check, timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if check():return
        time.sleep(.005)
    raise AssertionError('Local validation deadline exceeded')


def distribution(values):
    ordered=sorted(values)
    return {'samples':len(values),'p50_ms':round(ordered[math.ceil(len(values)*.50)-1],2),
            'p95_ms':round(ordered[math.ceil(len(values)*.95)-1],2),'max_ms':round(max(values),2)}


def main():
    schema='smartcare_kpi_'+uuid4().hex
    factory=lambda:PostgresStore(schema=schema,initialize=False)
    patients=load_patients()
    for p in patients.values():
        p.patient_id='KPI_'+p.patient_id+'_'+uuid4().hex[:6]
        p.consent=Consent(p.patient_id,True)
    patients={p.patient_id:p for p in patients.values()}
    policy={'timeout_seconds':30,'startup_grace_seconds':30,'devices':[
        {'patient_id':pid,'device_id':'SIM_'+pid,'parameters':list(PARAMETER_DEFINITIONS)} for pid in patients]}
    url='https://127.0.0.1:8443'
    report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'status':'FAILED',
        'scope':'Local synthetic prototype acceptance; sequential acquisition, not a load or clinical accuracy benchmark.',
        'environment':{'python':platform.python_version(),'os':platform.system(),
            'packages':{name:version(name) for name in ('fastapi','psycopg','paho-mqtt','cryptography')}},
        'config_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'config').glob('*.json'))},
        'targets':{'delivery_percent':100,'duplicate_rows':0,'invalid_rows':0,
                   'capture_to_commit_p95_ms_max':2000,'overview_https_p95_ms_max':1000},'checks':{}}
    server=None
    try:
        with PostgresStore(schema=schema):pass
        password=secrets.token_urlsafe(24)
        AuthenticationService(factory).create_user('kpi-admin',password,'ADMIN',bootstrap=True)
        app=create_app(schema=schema,patients=patients,store_factory=factory,port=8883,
            mqtt_security=TLSService.from_file(ROOT/'.secrets/receiver.json'),connection_policy=policy)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8443,log_level='warning',
            proxy_headers=False,ssl_certfile=str(ROOT/'.secrets/tls/web.crt'),ssl_keyfile=str(ROOT/'.secrets/tls/web.key')))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        wait_for(lambda:server.started and app.state.receiver.snapshot()['connected'])
        latencies=[];readings=[];invalid_ids=[]
        with factory() as store, MQTTPublisher(port=8883,security=TLSService.from_file(ROOT/'.secrets/simulator.json')) as publisher:
            repo=PostgresMeasurementRepository(store)
            start=time.perf_counter()
            for cycle in range(6):
                cycle_start=time.monotonic()
                for m in cycle_measurements(patients,cycle,'normal'):
                    # Capture immediately before emission; poll observes a committed, decryptable row.
                    m.timestamp=datetime.now(timezone.utc)
                    before=time.perf_counter()
                    publisher.publish(m)
                    wait_for(lambda:repo.get_payload(m.measurement_id) is not None)
                    latencies.append((time.perf_counter()-before)*1000)
                    readings.append(m)
                # The hypertension trend requires at least 10 seconds of observations.
                time.sleep(max(0,2.5-(time.monotonic()-cycle_start)))
            duration=time.perf_counter()-start
            for m in readings[:10]:publisher.publish(m)
            for changes in ({'value':10000},{'unit':'invalid'},{'quality':'invalid'}):
                data=readings[0].to_dict();data.update(changes,measurement_id=str(uuid4()),reading_id=str(uuid4()))
                invalid_ids.append(data['measurement_id'])
                publisher.client.publish(f"health/{data['patient_id']}/vitals",json.dumps(data),qos=1).wait_for_publish(5)
            marker=cycle_measurements(patients,7,'normal')[0]
            publisher.publish(marker)
            wait_for(lambda:repo.get_payload(marker.measurement_id) is not None)
            count=repo.count()
            report['metrics']={'unique_valid_sent':len(readings)+1,'stored':count,
                'delivery_percent':100*count/(len(readings)+1),'replayed_messages':10,
                'duplicate_rows':count-(len(readings)+1),'invalid_sent':len(invalid_ids),
                'invalid_rows':sum(repo.get_payload(mid) is not None for mid in invalid_ids),
                'capture_to_commit':distribution(latencies),
                'observed_serial_readings_per_second':round(len(readings)/duration,2)}
            wait_for(lambda:set(app.state.receiver.snapshot()['states'].values())=={'NORMAL'})
            report['checks']['three_normal_patients']=True
        with httpx.Client(base_url=url,verify=ssl.create_default_context(cafile=str(ROOT/'.secrets/tls/ca.crt')),
                          headers={'Origin':url},timeout=10) as client:
            assert client.get('/api/overview').status_code==401
            response=client.post('/api/auth/login',json={'username':'kpi-admin','password':password})
            assert response.status_code==200
            api=[]
            for _ in range(25):
                before=time.perf_counter();response=client.get('/api/overview');response.raise_for_status()
                api.append((time.perf_counter()-before)*1000)
                assert response.json()['totals']['measurements']==len(readings)+1
            report['metrics']['overview_https']=distribution(api)
            report['checks']['tls_hostname_and_ca_verified']=True
        metrics=report['metrics'];targets=report['targets']
        for field in ('delivery_percent','duplicate_rows','invalid_rows'):
            report['checks'][field]=metrics[field]==targets[field]
        report['checks']['capture_to_commit_p95']=metrics['capture_to_commit']['p95_ms']<targets['capture_to_commit_p95_ms_max']
        report['checks']['overview_https_p95']=metrics['overview_https']['p95_ms']<targets['overview_https_p95_ms_max']
        assert all(report['checks'].values()),'One or more acceptance targets failed'
        report['status']='PASSED'
    except Exception as error:
        report['error_type']=type(error).__name__
        raise
    finally:
        if server:
            server.should_exit=True;thread.join(timeout=12)
        with PostgresStore(schema=schema) as store:
            store.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        output=ROOT/'reports';output.mkdir(exist_ok=True)
        (output/'step12_kpi.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        metrics=report.get('metrics',{})
        rows='\n'.join(f'| {key} | `{json.dumps(value,ensure_ascii=False)}` |' for key,value in metrics.items())
        (output/'step12_kpi.md').write_text(f"# Mesures de validation Smartcare\n\n{report['timestamp_utc']} — **{report['status']}**\n\n"
            'Chaîne locale réelle : MQTT/TLS → Mosquitto → Node-RED → moteur Python → PostgreSQL chiffré → API HTTPS.\n\n'
            '| Indicateur | Résultat |\n| --- | --- |\n'+rows+'\n\n'
            'Cibles : 100 % livrés, aucun doublon ni message invalide stocké, p95 acquisition/commit < 2 s, '
            'p95 API < 1 s. Percentiles au rang supérieur. Acquisition séquentielle ; le débit observé n’est pas une capacité maximale. '
            'Les mesures incluent le sondage SQL (5 ms), le déchiffrement et les appels HTTPS locaux. '
            'Le rafraîchissement visuel toutes les 3 s est distinct. Aucun résultat de précision médicale n’est déduit.\n\n'
            'Environnement, seuils et empreintes des configurations : [rapport JSON](step12_kpi.json).\n')
    print('OK : KPI mesurés et critères satisfaits — reports/step12_kpi.md')


if __name__=='__main__':main()
