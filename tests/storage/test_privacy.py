from uuid import uuid4
import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from src.domain import Alert, Patient
from src.domain.consent import Consent
from src.processing.persistent_monitoring import PersistentMonitoring
from src.repositories.consent_repository import ConsentRepository, ConsentRequired
from src.repositories.postgres_store import PostgresStore, ROOT
from src.repositories.postgres_repositories import PostgresMeasurementRepository, PostgresAlertRepository
from src.security.authentication import AuthenticationService
from src.security.encryption import EncryptionService, EncryptionError
from src.web.app import create_app
from tests.storage.test_postgres import measurement

pytestmark=pytest.mark.postgres_integration
PASSWORD='Test-privacy-password-123'


def test_encrypted_payloads_survive_reopen_and_do_not_expose_values(postgres_schema):
    m=measurement(value=87.125)
    with PostgresStore(schema=postgres_schema) as store:
        PostgresMeasurementRepository(store).save(m)
        PostgresAlertRepository(store).save(Alert('private-alert','P001','WARNING','Private physiological observation',rule_id='rule'))
        for table in ['measurements','alerts']:
            payload=store.connection.execute(sql.SQL('SELECT payload FROM {}').format(sql.Identifier(table))).fetchone()['payload']
            assert set(payload)=={'encrypted','token'}
            assert '87.125' not in json.dumps(payload) and 'Private physiological' not in json.dumps(payload)
        columns=store.connection.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',(postgres_schema,'measurements')).fetchall()
        assert 'value' not in {row['column_name'] for row in columns}
    with PostgresStore(schema=postgres_schema) as store:
        assert PostgresMeasurementRepository(store).get_payload(m.measurement_id)['value']==87.125
        assert PostgresAlertRepository(store).getActive()[0].message=='Private physiological observation'


def test_missing_wrong_key_and_record_substitution_fail_closed(postgres_schema,tmp_path,monkeypatch):
    first,second=measurement(),measurement(85)
    with PostgresStore(schema=postgres_schema) as store:
        repo=PostgresMeasurementRepository(store);repo.save(first);repo.save(second)
        envelope=store.connection.execute('SELECT payload FROM measurements WHERE measurement_id=%s',(first.measurement_id,)).fetchone()['payload']
        store.connection.execute('UPDATE measurements SET payload=%s WHERE measurement_id=%s',(Jsonb(envelope),second.measurement_id))
        with pytest.raises(EncryptionError):
            repo.get_payload(second.measurement_id)
    wrong=tmp_path/'wrong.key';wrong.write_bytes(Fernet.generate_key())
    with monkeypatch.context() as env:
        env.setenv('SMARTCARE_STORAGE_KEY_FILE',str(wrong))
        with pytest.raises(EncryptionError):PostgresStore(schema=postgres_schema)
        env.setenv('SMARTCARE_STORAGE_KEY_FILE',str(tmp_path/'absent.key'))
        with pytest.raises(EncryptionError):PostgresStore(schema=postgres_schema)


def test_upgrade_encrypts_old_rows_without_losing_data(postgres_schema):
    m=measurement();data=m.to_dict()
    with PostgresStore(schema=postgres_schema,initialize=False) as legacy:
        db=legacy.connection
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(postgres_schema)))
        db.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)')
        for version,name in [(1,'001_initial.sql'),(2,'002_security.sql'),(3,'003_connections.sql')]:
            db.execute((ROOT/'infra/postgres/migrations'/name).read_text())
            db.execute('INSERT INTO schema_migrations VALUES (%s)',(version,))
        db.execute('INSERT INTO measurements VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            tuple(data[k] for k in ('measurement_id','patient_id','device_id','reading_id','parameter','value','unit','quality','timestamp'))+(Jsonb(data),))
        db.execute('INSERT INTO measurement_receipts VALUES (%s,%s)',(m.measurement_id,m.measurement_id))
    with PostgresStore(schema=postgres_schema) as migrated:
        assert PostgresMeasurementRepository(migrated).get_payload(m.measurement_id)==data
        assert migrated.connection.execute('SELECT payload FROM measurements').fetchone()['payload']['encrypted']=='fernet-v1'


def test_consent_is_required_revocable_and_audited_without_deleting_history(postgres_schema):
    with PostgresStore(schema=postgres_schema):pass
    factory=lambda:PostgresStore(schema=postgres_schema,initialize=False)
    auth=AuthenticationService(factory)
    admin=auth.create_user('admin',PASSWORD,'ADMIN',bootstrap=True)
    auth.create_user('doctor',PASSWORD,'DOCTOR',admin)
    patient=Patient('P001','Patient fictif')
    with PostgresStore(schema=postgres_schema) as store:
        pipeline=PersistentMonitoring(store)
        with pytest.raises(ConsentRequired):pipeline.process([measurement()],patient)
        assert pipeline.measurements.count()==0
        ConsentRepository(store).set('P001',True,admin)
        pipeline.process([measurement()],patient)
        assert pipeline.measurements.count()==1
        app=create_app(ingest=False,patients={'P001':patient},store_factory=factory)
        with TestClient(app,base_url='https://testserver') as client:
            login=client.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'admin','password':PASSWORD})
            client.headers.update({'Origin':'https://testserver','X-CSRF-Token':login.json()['csrf_token']})
            assert client.get('/api/overview').json()['totals']['measurements']==1
            assert client.put('/api/admin/consents/P001',json={'granted':False}).status_code==200
            overview=client.get('/api/overview').json()
            assert overview['totals']['measurements']==0 and overview['patients'][0]['latest']=={}
            for endpoint in ['/api/patients/P001/history','/api/patients/P001/events','/api/alerts?patient_id=P001']:
                assert client.get(endpoint).status_code==403
            assert client.get('/api/alerts').json()['items']==[]
            with pytest.raises(ConsentRequired):pipeline.process([measurement()],patient)
            assert pipeline.measurements.count()==1
            assert client.put('/api/admin/consents/P001',json={'granted':True}).status_code==200
            assert client.get('/api/patients/P001/history').status_code==200
            assert client.put('/api/admin/consents/P001',json={'granted':'yes'}).status_code==422
            assert client.put('/api/admin/consents/P999',json={'granted':True}).status_code==404
            login=client.post('/api/auth/login',json={'username':'doctor','password':PASSWORD})
            client.headers['X-CSRF-Token']=login.json()['csrf_token']
            assert client.get('/api/admin/consents').status_code==403
            assert client.put('/api/admin/consents/P001',json={'granted':True}).status_code==403
    actions={r['action'] for r in auth.list_audit()}
    assert {'CONSENT_GRANTED','CONSENT_REVOKED'}<=actions


def test_recorded_revocation_overrides_simulation_default_after_restart(postgres_schema):
    with PostgresStore(schema=postgres_schema) as store:
        auth=AuthenticationService(lambda:PostgresStore(schema=postgres_schema,initialize=False))
        admin=auth.create_user('admin',PASSWORD,'ADMIN',bootstrap=True)
        patient=Patient('P001','Demo',consent=Consent('P001',True))
        ConsentRepository(store).set('P001',False,admin)
    with PostgresStore(schema=postgres_schema) as store:
        assert not ConsentRepository(store).get('P001',patient)['granted']
        with pytest.raises(ConsentRequired):PersistentMonitoring(store).process([measurement()],patient)
