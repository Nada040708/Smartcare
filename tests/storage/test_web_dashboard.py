from datetime import datetime, timedelta, timezone
from uuid import uuid4
import time

import pytest
from fastapi.testclient import TestClient

from src.domain import Measurement, Patient, Alert, DiabetesProfile
from src.repositories.postgres_store import PostgresStore
from src.repositories.postgres_repositories import PostgresMeasurementRepository, PostgresAlertRepository, PostgresEventRepository
from src.web.app import create_app
from src.web.queries import DashboardQueries
from src.web.receiver import MonitoringReceiver
from src.web.security import require_reader
from src.domain.consent import Consent

pytestmark=pytest.mark.postgres_integration


def reading(pid, value=80, *, timestamp=None, parameter='heart_rate', unit='bpm'):
    return Measurement(str(uuid4()),pid,device_id='SIM_WEB',parameter=parameter,value=value,unit=unit,
                       timestamp=timestamp or datetime.now(timezone.utc),quality='valid')


def app_for(schema, patients=None, receiver=None):
    app = create_app(schema=schema, patients=patients, ingest=False, receiver=receiver,
                     store_factory=lambda:PostgresStore(schema=schema,initialize=False))
    app.dependency_overrides[require_reader] = lambda: {'role': 'DOCTOR', 'active': True}
    return app


def test_empty_dashboard_has_configured_patients_and_no_invented_measurements(postgres_schema):
    with PostgresStore(schema=postgres_schema):
        pass
    with TestClient(app_for(postgres_schema)) as client:
        body=client.get('/api/overview').json()
        assert body['totals']==dict(patients=3,active_alerts=0,critical_patients=0,measurements=0)
        assert all(p['state']=='SURVEILLANCE' and not p['latest'] for p in body['patients'])
        assert client.get('/api/patients/P001/history').json()['items']==[]
        assert client.get('/api/patients/P999/history').status_code==404
        assert client.get('/api/alerts?patient_id=P999').status_code==404
        assert client.get('/api/patients/P999/events').status_code==404


def test_history_returns_newest_window_in_order_without_patient_leak(postgres_schema):
    now=datetime.now(timezone.utc)
    with PostgresStore(schema=postgres_schema) as store:
        repo=PostgresMeasurementRepository(store)
        for i in range(5):
            repo.save(reading('P001',80+i,timestamp=now-timedelta(seconds=5-i)))
        repo.save(reading('P001',90,timestamp=now-timedelta(days=2)))
        repo.save(reading('P002',200))
    with TestClient(app_for(postgres_schema)) as client:
        response=client.get('/api/patients/P001/history?parameter=heart_rate&minutes=60&limit=3').json()
        assert [m['value'] for m in response['items']]==[82,83,84]
        assert response['truncated'] is True
        assert all(m['patient_id']=='P001' for m in response['items'])
        assert client.get('/api/patients/P001/history?parameter=spo2').json()['items']==[]


def test_summary_marks_old_readings_and_never_replays_a_historical_normal_state(postgres_schema):
    now=datetime.now(timezone.utc)
    patients={'P001':Patient('P001','Patient 1',consent=Consent('P001',True))}
    with PostgresStore(schema=postgres_schema) as store:
        repo=PostgresMeasurementRepository(store)
        repo.save(reading('P001',timestamp=now-timedelta(seconds=121)))
        runtime=dict(running=True,connected=True,evaluated_at=now.isoformat(),states={'P001':'NORMAL'})
        result=DashboardQueries(store,patients,runtime,now=now).overview()['patients'][0]
        assert result['latest']['heart_rate']['stale'] is True
        assert result['state']=='SURVEILLANCE'
        repo.save(reading('P001',timestamp=now))
        assert DashboardQueries(store,patients,runtime,now=now).overview()['patients'][0]['state']=='NORMAL'
        runtime['evaluated_at']=(now-timedelta(seconds=10)).isoformat()
        assert DashboardQueries(store,patients,runtime,now=now).overview()['patients'][0]['state']=='SURVEILLANCE'
        active=Alert('ACTIVE','P001','CRITICAL','Alerte démo',rule_id='test')
        PostgresAlertRepository(store).save(active)
        runtime['states']['P001']='NORMAL'
        result=DashboardQueries(store,patients,runtime,now=now).overview()['patients'][0]
        assert result['state']=='CRITICAL' and result['active_alerts']==1


def test_unregistered_historical_patient_remains_visible_without_assigning_profiles(postgres_schema):
    with PostgresStore(schema=postgres_schema) as store:
        PostgresMeasurementRepository(store).save(reading('ARCHIVE'))
    with TestClient(app_for(postgres_schema)) as client:
        historical=next(p for p in client.get('/api/overview').json()['patients'] if p['patient_id']=='ARCHIVE')
        assert historical['configured'] is False and historical['profiles']==[]
        assert historical['state']=='SURVEILLANCE'
        assert historical['latest']=={} and historical['consent']['granted'] is False
        assert client.get('/api/patients/ARCHIVE/history').status_code==403


def test_alert_filters_and_pagination_do_not_write_to_storage(postgres_schema):
    now=datetime.now(timezone.utc)
    with PostgresStore(schema=postgres_schema) as store:
        alerts=PostgresAlertRepository(store)
        for i in range(13):
            alert=Alert(f'A{i:02}','P001','WARNING','Même texte',timestamp=now-timedelta(minutes=i+2),rule_id=f'rule{i}')
            alert.resolve(timestamp=now,reason='RECOVERY_CONFIRMED')
            alerts.save(alert)
        alerts.save(Alert('OTHER','P002','CRITICAL','Autre patient',rule_id='rule'))
    with TestClient(app_for(postgres_schema)) as client:
        query='/api/alerts?patient_id=P001&status=RESOLVED&severity=WARNING&limit=10'
        first=client.get(query).json()
        second=client.get(query+'&offset=10').json()
        assert first['total']==13 and len(first['items'])==10 and len(second['items'])==3
        assert not {a['alert_id'] for a in first['items']} & {a['alert_id'] for a in second['items']}
        assert client.get('/api/alerts?patient_id=P001').json()['total']==0
        assert client.get('/api/overview').json()['totals']['active_alerts']==1
    with PostgresStore(schema=postgres_schema) as store:
        assert PostgresAlertRepository(store).count()==14
        assert PostgresEventRepository(store).count()==0


def wait_for(check, timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if check():
            return
        time.sleep(.05)
    raise AssertionError('Expected live condition was not reached')


@pytest.mark.mqtt_integration
def test_mqtt_node_red_receiver_database_and_http_api_end_to_end(postgres_schema):
    from src.communication import MQTTPublisher
    pid='WEB_'+uuid4().hex[:8]
    patients={pid:Patient(pid,'Patient test',profiles=[DiabetesProfile()],consent=Consent(pid,True))}
    receiver=MonitoringReceiver(patients,schema=postgres_schema)
    with PostgresStore(schema=postgres_schema):
        pass
    with TestClient(app_for(postgres_schema,patients,receiver)) as client:
        wait_for(lambda:receiver.snapshot()['connected'])
        measure=reading(pid,230,parameter='glucose',unit='mg/dL')
        with MQTTPublisher() as publisher:
            publisher.publish(measure)
            wait_for(lambda:client.get('/api/alerts').json()['total']==1)
            publisher.publish(measure)
            wait_for(lambda:receiver.snapshot()['processed']>=2)
        body=client.get('/api/overview').json()
        assert body['totals']['measurements']==1
        assert body['patients'][0]['latest']['glucose']['value']==230
        assert body['patients'][0]['state']=='ALERT'
        assert client.get('/api/alerts').json()['items'][0]['occurrences']==1
        assert client.get(f'/api/patients/{pid}/history?parameter=glucose').json()['items'][0]['measurement_id']==measure.measurement_id
        assert client.get(f'/api/patients/{pid}/events').json()['items']
    assert not receiver.snapshot()['running']
    with PostgresStore(schema=postgres_schema) as reopened:
        reopened.acquire_writer()  # Shutdown released the stateful writer lock.
