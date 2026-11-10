from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from src.repositories.postgres_store import PostgresStore
from src.security.authentication import AuthenticationService, AuthError, HASHER, digest
from src.web.app import create_app
from src.web.security import COOKIE
from src.domain import Alert
from src.repositories.postgres_repositories import PostgresAlertRepository

pytestmark = pytest.mark.postgres_integration
PASSWORD = 'Test-only-password-1234'
ORIGIN = 'https://testserver'


@pytest.fixture
def security(postgres_schema):
    with PostgresStore(schema=postgres_schema):
        pass
    factory = lambda: PostgresStore(schema=postgres_schema, initialize=False)
    service = AuthenticationService(factory)
    admin = service.create_user('admin', PASSWORD, 'ADMIN', bootstrap=True)
    app = create_app(ingest=False, store_factory=factory)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, service, factory, admin


def login(client, username='admin', password=PASSWORD):
    response = client.post('/api/auth/login', json={'username': username, 'password': password}, headers={'Origin': ORIGIN})
    assert response.status_code == 200, response.text
    client.headers.update({'Origin': ORIGIN, 'X-CSRF-Token': response.json()['csrf_token']})
    return response


@pytest.mark.parametrize('url', ['/api/overview', '/api/alerts', '/api/patients/P001/history',
                                 '/api/patients/P001/events', '/api/auth/me', '/api/admin/users', '/api/admin/audit'])
def test_every_data_endpoint_requires_authentication(security, url):
    client, *_ = security
    assert client.get(url).status_code == 401
    assert client.get('/', follow_redirects=False).headers['location'] == '/login'
    assert client.get('/login').status_code == 200
    assert client.get('/docs').status_code == 404
    assert client.get('/openapi.json').status_code == 404


def test_password_hash_cookie_flags_session_rotation_and_logout(security):
    client, service, factory, admin = security
    response = login(client)
    cookie = response.headers['set-cookie'].lower()
    assert all(flag in cookie for flag in ['httponly', 'secure', 'samesite=strict', 'path=/'])
    token = client.cookies.get(COOKIE)
    with factory() as store:
        row = store.connection.execute('SELECT password_hash FROM users').fetchone()
        assert row['password_hash'].startswith('$argon2id$') and HASHER.verify(row['password_hash'], PASSWORD)
        assert store.connection.execute('SELECT token_hash FROM auth_sessions').fetchone()['token_hash'] == digest(token)
    assert client.get('/api/overview').status_code == 200
    assert client.get('/api/auth/me').json()['user']['role'] == 'ADMIN'
    login(client)
    with pytest.raises(AuthError):
        service.authenticate(token)
    token = client.cookies.get(COOKIE)
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/overview').status_code == 401
    with pytest.raises(AuthError):
        service.authenticate(token)


@pytest.mark.parametrize('role', ['DOCTOR', 'NURSE'])
def test_clinicians_read_but_cannot_manage_users_or_audit(security, role):
    client, service, _, admin = security
    service.create_user('clinician', PASSWORD, role, admin)
    login(client, 'clinician')
    assert client.get('/api/overview').status_code == 200
    for url in ['/admin', '/api/admin/users', '/api/admin/audit']:
        assert client.get(url).status_code == 403
    assert client.post('/api/admin/users', json={'username':'intruder','password':PASSWORD,'role':'ADMIN'}).status_code == 403
    assert client.patch(f"/api/admin/users/{admin['user_id']}", json={'active':False}).status_code == 403
    assert any(row['action']=='ACCESS_DENIED' for row in service.list_audit())


def test_csrf_and_cross_origin_login_are_refused(security):
    client, *_ = security
    body = {'username':'admin','password':PASSWORD}
    assert client.post('/api/auth/login', json=body).status_code == 403
    assert client.post('/api/auth/login', json=body, headers={'Origin':'https://evil.example'}).status_code == 403
    login(client)
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token':'wrong'}).status_code == 403
    assert client.post('/api/auth/logout', headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.get('/api/auth/me').status_code == 200
    assert client.get('/api/overview', headers={'Host':'evil.example'}).status_code == 400


def test_admin_management_revokes_sessions_and_protects_last_admin(security):
    client, service, _, admin = security
    login(client)
    created = client.post('/api/admin/users', json={'username':'doctor','password':PASSWORD,'role':'DOCTOR'})
    assert created.status_code == 201
    uid = created.json()['user_id']
    user, token = service.login('doctor', PASSWORD, 'another-client')
    assert client.patch(f'/api/admin/users/{uid}', json={'active':False}).status_code == 200
    with pytest.raises(AuthError):
        service.authenticate(token)
    with pytest.raises(AuthError):
        service.login('doctor', PASSWORD, 'another-client')
    assert client.patch(f'/api/admin/users/{uid}', json={'active':True,'role':'NURSE','password':'Replacement-pass-123'}).status_code == 200
    with pytest.raises(AuthError):
        service.login('doctor', PASSWORD, 'another-client')
    assert service.login('doctor', 'Replacement-pass-123', 'another-client')[0]['role'] == 'NURSE'
    for changes in [{'active':False}, {'role':'DOCTOR'}]:
        assert client.patch(f"/api/admin/users/{admin['user_id']}", json=changes).status_code == 409
    assert client.patch(f'/api/admin/users/{uuid4()}', json={'active':False}).status_code == 404
    assert client.patch(f'/api/admin/users/{uid}', json={'active':None}).status_code == 422
    assert client.patch(f'/api/admin/users/{uid}', json={'active':'false'}).status_code == 422
    assert client.post('/api/admin/users', json={'username':'doctor','password':PASSWORD,'role':'ADMIN'}).status_code == 409
    with pytest.raises(AuthError):
        service.create_user('second', PASSWORD, 'ADMIN', bootstrap=True)
    for url in ['/api/admin/users', '/api/admin/audit']:
        text = client.get(url).text
        assert PASSWORD not in text and '$argon2' not in text and token not in text


@pytest.mark.parametrize('column,age', [('expires_at', "now()-interval '1 second'"),
                                     ('last_seen_at', "now()-interval '31 minutes'")])
def test_expired_and_idle_sessions_are_rejected(security, column, age):
    client, _, factory, _ = security
    login(client)
    with factory() as store:
        # The SQL fragments come exclusively from the fixed test parameter list.
        store.connection.execute(f'UPDATE auth_sessions SET {column}={age}')
    assert client.get('/api/overview').status_code == 401


def test_failed_login_is_generic_rate_limited_and_persisted(security):
    client, service, factory, _ = security
    def attempt(name):
        return client.post('/api/auth/login', json={'username':name,'password':'Wrong-password-123'}, headers={'Origin':ORIGIN})
    assert attempt('admin').json() == attempt('unknown').json()
    for _ in range(9):
        assert attempt('admin').status_code == 401
    assert attempt('admin').status_code == 429
    # Constructing another service does not reset the database limiter.
    with pytest.raises(AuthError) as caught:
        AuthenticationService(factory).login('admin', PASSWORD, 'new-client')
    assert caught.value.status == 429
    with factory() as store:
        store.connection.execute("UPDATE auth_throttle SET expires_at=now()-interval '1 second'")
    login(client)
    actions = [row['action'] for row in service.list_audit()]
    assert 'LOGIN_FAILED' in actions and 'LOGIN_THROTTLED' in actions and 'LOGIN_SUCCESS' in actions


def test_invalid_bodies_do_not_echo_passwords_and_forged_cookies_fail(security):
    client, *_ = security
    response = client.post('/api/auth/login', json={'username':'admin','password':PASSWORD*20}, headers={'Origin':ORIGIN})
    assert response.status_code == 422 and PASSWORD not in response.text
    client.cookies.set(COOKIE, 'a'*43)
    assert client.get('/api/overview').status_code == 401


def test_two_admins_cannot_concurrently_disable_each_other_leaving_none(security):
    _, service, _, admin = security
    second = service.create_user('second', PASSWORD, 'ADMIN', admin)
    def disable(user):
        try:
            service.update_user(user['user_id'], {'active':False}, admin)
            return True
        except AuthError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(disable, [admin, second])) == 1
    assert len([u for u in service.list_users() if u['active'] and u['role']=='ADMIN']) == 1


def test_clinician_signup_waits_for_admin_approval(security):
    client, service, _, _ = security
    response = client.post('/api/auth/signup', headers={'Origin':ORIGIN}, json={
        'username':'new.doctor','password':PASSWORD,'role':'DOCTOR'})
    assert response.status_code == 201
    assert 'administrateur' in response.json()['message']
    pending = next(user for user in service.list_users() if user['username']=='new.doctor')
    assert pending['approval_status']=='PENDING' and pending['active'] is False
    with pytest.raises(AuthError):
        service.login('new.doctor',PASSWORD,'waiting-user')
    login(client)
    approved = client.patch(f"/api/admin/users/{pending['user_id']}", json={'active':True})
    assert approved.status_code==200 and approved.json()['approval_status']=='APPROVED'
    assert service.login('new.doctor',PASSWORD,'approved-user')[0]['role']=='DOCTOR'


def test_doctor_can_add_patient_but_nurse_cannot(security):
    client, service, factory, admin = security
    doctor=service.create_user('doctor.patient',PASSWORD,'DOCTOR',admin)
    nurse=service.create_user('nurse.patient',PASSWORD,'NURSE',admin)
    body={'patient_id':'P900','name':'Patient ajouté','profiles':['diabetes','hypertension'],
          'monitoring_enabled':True}
    login(client,'doctor.patient')
    assert client.post('/api/patient-registry',json=body).status_code==201
    with factory() as store:
        row=store.connection.execute("SELECT profiles FROM patient_registry WHERE patient_id='P900'").fetchone()
        assert row['profiles']==['diabetes','hypertension']
    login(client,'nurse.patient')
    assert client.post('/api/patient-registry',json=dict(body,patient_id='P901')).status_code==403


def test_nurse_can_contact_doctor_and_manually_resolve_alert(security):
    client, service, factory, admin = security
    doctor=service.create_user('doctor.alert',PASSWORD,'DOCTOR',admin)
    service.create_user('nurse.alert',PASSWORD,'NURSE',admin)
    with factory() as store:
        PostgresAlertRepository(store).save(Alert('MANUAL-A1','P001','CRITICAL','Action requise',rule_id='manual'))
    login(client,'nurse.alert')
    assert client.post('/api/alerts/MANUAL-A1/contact-doctor',json={'doctor_id':doctor['user_id']}).status_code==201
    resolved=client.post('/api/alerts/MANUAL-A1/resolve')
    assert resolved.status_code==200 and resolved.json()['status']=='RESOLVED'
    history=client.get('/api/alerts?status=ALL').json()['items']
    alert=next(item for item in history if item['alert_id']=='MANUAL-A1')
    assert alert['status']=='RESOLVED'
    assert [action['action'] for action in alert['actions']]==['DOCTOR_CONTACTED','RESOLVED']
