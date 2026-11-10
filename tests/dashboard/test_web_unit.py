import json
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.domain import Patient
from src.web.app import create_app as secured_app
from src.web.security import require_reader
from src.web.patients import load_patients
from src.web.receiver import MonitoringReceiver


def create_app(**kwargs):
    # These tests isolate dashboard validation/storage. Real auth is tested in test_security.py.
    app = secured_app(**kwargs)
    app.dependency_overrides[require_reader] = lambda: {'role': 'DOCTOR', 'active': True}
    return app


@pytest.mark.parametrize('records', [
    {}, [{'patient_id':'P','name':'Test','profiles':['unknown']}],
    [{'patient_id':'../bad','name':'Test','profiles':[]}],
    [{'patient_id':'P','name':'Test','profiles':[],'monitoring_enabled':'false'}],
    [{'patient_id':'P','name':'Test','profiles':[]}, {'patient_id':'P','name':'Other','profiles':[]}],
])
def test_patient_registry_rejects_ambiguous_configuration(tmp_path, records):
    path=tmp_path/'patients.json'
    path.write_text(json.dumps(records))
    with pytest.raises(ValueError):
        load_patients(path)


def test_db_failure_is_a_clear_503_without_leaking_configuration():
    def unavailable():
        raise psycopg.OperationalError('postgres://user:secret@private-db')
    with TestClient(create_app(ingest=False, store_factory=unavailable)) as client:
        response=client.get('/api/overview')
        assert response.status_code==503
        assert 'secret' not in response.text and 'private-db' not in response.text
        assert response.headers['cache-control']=='no-store'
        assert client.get('/').status_code==200
        assert client.get('/assets/app.js').status_code==200


@pytest.mark.parametrize('url', [
    '/api/patients/P001/history?parameter=bad', '/api/patients/P001/history?minutes=-1',
    '/api/patients/P001/history?limit=10000', '/api/alerts?status=BAD',
    '/api/alerts?offset=-1', '/api/alerts?severity=BAD',
])
def test_api_rejects_invalid_filters_before_querying(url):
    def never_called():
        raise AssertionError('Invalid request should not reach the database')
    with TestClient(create_app(ingest=False, store_factory=never_called)) as client:
        assert client.get(url).status_code==422


@pytest.mark.parametrize('topic,payload,retained', [
    ('health/P001/received', b'{}', True), ('health/P999/received', b'{}', False),
    ('health/P001/vitals', b'{}', False), ('health/P001/received', b'x'*65537, False),
])
def test_receiver_rejects_unsafe_receipts_before_processing(topic, payload, retained):
    receiver=MonitoringReceiver({'P001':Patient('P001','Patient 1')})
    with pytest.raises(ValueError):
        receiver.handle_message(None, topic, payload, retained)


def test_receiver_passes_original_payload_and_corresponding_patient_topic():
    patient=Patient('P001','Patient 1')
    calls=[]
    session=SimpleNamespace(process_payload=lambda *args, **kwargs: calls.append((args,kwargs)))
    receiver=MonitoringReceiver({'P001':patient})
    payload=b'{"patient_id":"P002"}'
    receiver.handle_message(session,'health/P001/received',payload)
    assert calls==[((payload,patient),{'topic':'health/P001/vitals'})]
