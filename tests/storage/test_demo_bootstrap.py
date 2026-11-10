from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from src.repositories.postgres_store import PostgresStore
from src.security.authentication import AuthenticationService, AuthError
from src.security.demo import initialize_demo_admin
from src.web.app import create_app

pytestmark = pytest.mark.postgres_integration
PASSWORD = 'Only-for-isolated-tests-123'


def factory_for(schema):
    with PostgresStore(schema=schema):
        pass
    return lambda: PostgresStore(schema=schema, initialize=False)


def test_first_start_login_logout_second_start_never_resets_password(postgres_schema):
    factory = factory_for(postgres_schema)
    assert initialize_demo_admin(factory, local_demo=True, password=PASSWORD)
    service = AuthenticationService(factory)
    with factory() as store:
        before = store.connection.execute('SELECT user_id,password_hash FROM users').fetchone()
    assert not initialize_demo_admin(factory, local_demo=True, password='Different-valid-password')
    with factory() as store:
        assert store.connection.execute('SELECT user_id,password_hash FROM users').fetchone() == before
    with TestClient(create_app(ingest=False,store_factory=factory),base_url='https://testserver') as client:
        for route in ['/', '/alerts', '/admin']:
            assert client.get(route,follow_redirects=False).headers['location']=='/login'
        for filename in ['index.html','alerts.html','admin.html']:
            assert client.get('/assets/'+filename).status_code==404
        login=client.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'admin','password':PASSWORD})
        assert login.status_code==200
        client.headers.update({'Origin':'https://testserver','X-CSRF-Token':login.json()['csrf_token']})
        assert all(client.get(route).status_code==200 for route in ['/', '/alerts', '/admin'])
        assert client.post('/api/auth/logout').status_code==200
        assert client.get('/api/overview').status_code==401
    assert len(service.list_users())==1


@pytest.mark.parametrize('password',[None,'short','x'*129])
def test_invalid_initial_password_leaves_database_empty(postgres_schema,password):
    factory=factory_for(postgres_schema)
    with pytest.raises(ValueError):initialize_demo_admin(factory,local_demo=True,password=password)
    assert AuthenticationService(factory).list_users()==[]


def test_normal_mode_never_prompts_or_creates_and_existing_accounts_win(postgres_schema):
    factory=factory_for(postgres_schema)
    def forbidden():raise AssertionError('No prompt permitted')
    assert not initialize_demo_admin(factory,password=PASSWORD,prompt=forbidden)
    service=AuthenticationService(factory)
    service.create_user('existing',PASSWORD,'ADMIN',bootstrap=True)
    assert not initialize_demo_admin(factory,local_demo=True,password='bad',prompt=forbidden)
    assert [u['username'] for u in service.list_users()]==['existing']


def test_concurrent_first_start_creates_one_account(postgres_schema):
    factory=factory_for(postgres_schema)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:initialize_demo_admin(factory,local_demo=True,password=PASSWORD),range(2)))
    assert sorted(results)==[False,True]
    assert len(AuthenticationService(factory).list_users())==1


@pytest.mark.parametrize('role',['DOCTOR','NURSE'])
def test_demo_does_not_change_role_guards_or_last_admin_rule(postgres_schema,role):
    factory=factory_for(postgres_schema)
    initialize_demo_admin(factory,local_demo=True,password=PASSWORD)
    service=AuthenticationService(factory);admin=service.list_users()[0]
    with pytest.raises(AuthError):service.update_user(admin['user_id'],{'active':False},admin)
    service.create_user('clinician',PASSWORD,role,admin)
    with TestClient(create_app(ingest=False,store_factory=factory,demo_mode=True),base_url='https://testserver') as client:
        response=client.post('/api/auth/login',headers={'Origin':'https://testserver'},json={'username':'clinician','password':PASSWORD})
        client.headers.update({'Origin':'https://testserver','X-CSRF-Token':response.json()['csrf_token']})
        assert client.get('/alerts').status_code==200
        for url in ['/admin','/api/admin/users','/api/admin/consents','/api/admin/audit']:
            assert client.get(url).status_code==403
        assert client.put('/api/admin/consents/P001',json={'granted':False}).status_code==403
