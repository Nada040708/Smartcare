from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import socket
import ssl
import threading
import time
from uuid import uuid4

import paho.mqtt.client as mqtt
import pytest

from src.communication import MQTTPublisher
from src.communication.tls import TLSService, MQTTAuthentication
from src.domain import Measurement, Patient
from src.repositories.postgres_store import PostgresStore
from src.repositories.postgres_repositories import PostgresMeasurementRepository
from src.web.receiver import MonitoringReceiver
from src.domain.consent import Consent

pytestmark = pytest.mark.tls_integration
SECRETS = Path(__file__).resolve().parents[2]/'.secrets'


def security(name):
    return TLSService.from_file(SECRETS/f'{name}.json')


def wait_for(check):
    deadline = time.monotonic()+10
    while time.monotonic()<deadline:
        if check():
            return
        time.sleep(.05)
    raise AssertionError('Secure pipeline did not reach the expected state')


@pytest.mark.postgres_integration
def test_tls_publisher_node_red_receiver_and_postgresql(postgres_schema):
    pid = 'TLS_' + uuid4().hex[:8]
    with PostgresStore(schema=postgres_schema):
        pass
    receiver = MonitoringReceiver({pid:Patient(pid,'Patient TLS fictif',consent=Consent(pid,True))},schema=postgres_schema,
                                  port=8883,security=security('receiver'))
    receiver.start()
    try:
        wait_for(lambda:receiver.snapshot()['connected'])
        measure = Measurement(str(uuid4()),pid,device_id='SIM_TLS',parameter='heart_rate',value=84,
                              unit='bpm',quality='valid',timestamp=datetime.now(timezone.utc))
        with MQTTPublisher(port=8883,security=security('simulator')) as publisher:
            publisher.publish(measure)
        wait_for(lambda:receiver.snapshot()['processed']>=1)
        with PostgresStore(schema=postgres_schema) as store:
            assert PostgresMeasurementRepository(store).get_payload(measure.measurement_id)['value']==84
    finally:
        receiver.stop()


def test_bad_password_anonymous_and_untrusted_ca_are_refused():
    valid = security('simulator')
    wrong = replace(valid,authentication=MQTTAuthentication('simulator','wrong'))
    with pytest.raises(ConnectionError):
        with MQTTPublisher(port=8883,security=wrong,timeout=2):
            pass
    connected = threading.Event()
    reasons = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.tls_set_context(ssl.create_default_context(cafile=str(SECRETS/'tls/ca.crt')))
    client.on_connect = lambda c,u,f,r,p: (reasons.append(r),connected.set())
    try:
        client.connect('localhost',8883)
        client.loop_start()
        assert connected.wait(3) and reasons[0].is_failure
    finally:
        client.disconnect(); client.loop_stop()
    with pytest.raises(ssl.SSLCertVerificationError):
        with MQTTPublisher(port=8883,security=replace(valid,ca_file=str(SECRETS/'tls/web.crt')),timeout=2):
            pass
    context = ssl.create_default_context(cafile=str(SECRETS/'tls/ca.crt'))
    with socket.create_connection(('127.0.0.1',8883),timeout=3) as sock:
        with pytest.raises(ssl.SSLCertVerificationError):
            context.wrap_socket(sock,server_hostname='wrong-host.example')


@pytest.mark.parametrize('identity,topic', [('simulator','health/P001/received'),
                                         ('receiver','health/P001/vitals'),
                                         ('node-red','health/P001/vitals')])
def test_acl_denies_forged_receipts_and_unauthorized_publications(identity,topic):
    ready, acknowledged = threading.Event(), threading.Event()
    reasons = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,protocol=mqtt.MQTTv5)
    security(identity).configure(client)
    client.on_connect = lambda c,u,f,r,p: ready.set() if not r.is_failure else None
    client.on_publish = lambda c,u,m,r,p: (reasons.append(r),acknowledged.set())
    try:
        client.connect('localhost',8883); client.loop_start()
        assert ready.wait(3)
        client.publish(topic,'{}',qos=1)
        assert acknowledged.wait(3) and reasons[0].is_failure
    finally:
        client.disconnect(); client.loop_stop()


def test_legacy_ports_are_closed_in_secure_profile():
    for port in (1883,1880):
        with socket.socket() as sock:
            sock.settimeout(1)
            assert sock.connect_ex(('127.0.0.1',port)) != 0


@pytest.mark.postgres_integration
def test_receiver_evaluates_timeouts_while_network_is_down_and_reconnects(postgres_schema,monkeypatch):
    pid='NET_'+uuid4().hex[:8]
    policy={'timeout_seconds':1,'startup_grace_seconds':1,'devices':[
        {'patient_id':pid,'device_id':'SIM_NET','parameters':['heart_rate']}]}
    unavailable=threading.Event()
    clients=[]
    original=mqtt.Client
    def client_factory(*args,**kwargs):
        client=original(*args,**kwargs)
        if str(kwargs.get('client_id','')).startswith('smartcare-web-'):
            connect=client.connect
            def simulated_network(*a,**kw):
                if unavailable.is_set():
                    raise ConnectionRefusedError('Simulated network interruption')
                return connect(*a,**kw)
            client.connect=simulated_network
            clients.append(client)
        return client
    monkeypatch.setattr(mqtt,'Client',client_factory)
    receiver=MonitoringReceiver({pid:Patient(pid,'Patient réseau',consent=Consent(pid,True))},schema=postgres_schema,port=8883,
        security=security('receiver'),connection_policy=policy)
    def measurement():
        return Measurement(str(uuid4()),pid,device_id='SIM_NET',parameter='heart_rate',value=84,
            unit='bpm',quality='valid',timestamp=datetime.now(timezone.utc))
    receiver.start()
    try:
        wait_for(lambda:receiver.snapshot()['connected'])
        with MQTTPublisher(port=8883,security=security('simulator')) as publisher:
            publisher.publish(measurement())
            wait_for(lambda:receiver.snapshot()['processed']==1)
            unavailable.set()
            clients[0].disconnect()
            wait_for(lambda:receiver.snapshot()['states'].get(pid)=='DISCONNECTED')
            assert receiver.snapshot()['running'] and not receiver.snapshot()['connected']
            with PostgresStore(schema=postgres_schema) as store:
                rows=store.connection.execute("SELECT payload FROM technical_events WHERE type='DISCONNECTED' AND status='ACTIVE'").fetchall()
                assert len(rows)==1
                incident_id=rows[0]['payload']['event_id']
            unavailable.clear()
            wait_for(lambda:receiver.snapshot()['connected'])
            publisher.publish(measurement())
            wait_for(lambda:receiver.snapshot()['processed']==2)
            with PostgresStore(schema=postgres_schema) as store:
                assert store.connection.execute('SELECT status FROM technical_events WHERE event_id=%s',(incident_id,)).fetchone()['status']=='RESOLVED'
                assert store.connection.execute('SELECT payload FROM device_connections').fetchone()['payload']['status']=='CONNECTED'
    finally:
        unavailable.clear()
        receiver.stop()


@pytest.mark.postgres_integration
def test_receiver_retries_after_temporary_database_outage(postgres_schema,monkeypatch):
    import psycopg
    from src.web import receiver as receiver_module
    attempts=[]
    def temporary_failure(*args,**kwargs):
        attempts.append(True)
        if len(attempts)==1:
            raise psycopg.OperationalError('Simulated database outage')
        return PostgresStore(*args,**kwargs)
    monkeypatch.setattr(receiver_module,'PostgresStore',temporary_failure)
    receiver=MonitoringReceiver({},schema=postgres_schema,port=8883,security=security('receiver'))
    receiver.start()
    try:
        wait_for(lambda:receiver.snapshot()['error']=='MONITORING_UNAVAILABLE')
        wait_for(lambda:receiver.snapshot()['connected'])
        assert len(attempts)>=2 and receiver.snapshot()['error'] is None
    finally:
        receiver.stop()
