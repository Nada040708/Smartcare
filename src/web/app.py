from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from pydantic import BaseModel, ConfigDict
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.processing import DataValidator
from src.repositories.postgres_store import PostgresStore
from .patients import load_patients, parameter_catalog, merge_registered_patients
from .queries import DashboardQueries
from .receiver import MonitoringReceiver
from .security import security_router, require_reader, require_admin, require_csrf, current_user, COOKIE
from src.security.authentication import AuthenticationService, AuthError, AuditLog
from src.security.encryption import EncryptionError
from src.repositories.consent_repository import ConsentRepository

STATIC = Path(__file__).parent / 'static'


def create_app(*, schema='smartcare', patients=None, ingest=True, broker='localhost', port=1883,
               store_factory=None, receiver=None, secure_cookies=True, mqtt_security=None, connection_policy=None, demo_mode=False):
    patients = load_patients() if patients is None else patients
    default_store_factory = store_factory is None
    store_factory = store_factory or (lambda: PostgresStore(schema=schema, initialize=False))
    receiver = receiver or (MonitoringReceiver(patients, schema=schema, broker=broker, port=port,
                            security=mqtt_security, connection_policy=connection_policy) if ingest else None)
    max_age = DataValidator().policy['max_age_seconds']

    @asynccontextmanager
    async def lifespan(app):
        # Startup migrations run once, not on every HTTP request.
        if default_store_factory:
            with store_factory() as store:
                merge_registered_patients(store, patients)
        if receiver:
            receiver.start()
        yield
        if receiver:
            receiver.stop()

    app = FastAPI(title='Smartcare — dashboard local', version='1.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.receiver = receiver
    app.state.auth = AuthenticationService(store_factory)
    app.state.secure_cookies = secure_cookies
    app.state.store_factory = store_factory
    app.state.patients = patients
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])
    app.include_router(security_router())

    @app.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        return response

    @app.exception_handler(AuthError)
    async def auth_error(request, error):
        if error.status == 401 and request.url.path in ('/', '/alerts', '/audit', '/admin'):
            return JSONResponse(status_code=303, content={'detail': error.message}, headers={'Location': '/login'})
        return JSONResponse(status_code=error.status, content={'detail': error.message},
                            headers={'Retry-After': '300'} if error.status == 429 else None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic's default error includes the supplied input, potentially a password.
        return JSONResponse(status_code=422, content={'detail': 'Requête invalide. Vérifiez les champs.'})

    @app.exception_handler(psycopg.Error)
    async def database_error(request, error):
        return JSONResponse(status_code=503, content={'detail': 'Les données sont momentanément indisponibles.'})

    @app.exception_handler(EncryptionError)
    async def encryption_error(request, error):
        return JSONResponse(status_code=503, content={'detail':'Les données protégées sont momentanément indisponibles.'})

    def runtime():
        return receiver.snapshot() if receiver else dict(running=False, connected=False, error=None, mode='history', states={})

    def queries(store):
        return DashboardQueries(store, patients, runtime(), max_age_seconds=max_age)

    def ensure_patient(reader, pid):
        if pid not in reader.known_ids():
            raise HTTPException(404, 'Patient introuvable')
        if not ConsentRepository(reader.store).get(pid,patients.get(pid))['granted']:
            raise HTTPException(403, 'Le consentement du patient est requis pour consulter ses données.')

    @app.get('/api/overview', dependencies=[Depends(require_reader)])
    def overview():
        with store_factory() as store, store.transaction():
            store.connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            result = queries(store).overview()
        result['parameters'] = parameter_catalog()
        result['demo_mode'] = demo_mode
        result['max_age_seconds'] = max_age
        return result

    @app.get('/api/patients/{patient_id}/history', dependencies=[Depends(require_reader)])
    def history(patient_id: str, parameter: str = 'heart_rate', minutes: int = Query(60, ge=1, le=10080),
                limit: int = Query(240, ge=1, le=600)):
        if parameter not in PARAMETER_DEFINITIONS:
            raise HTTPException(422, 'Paramètre inconnu')
        with store_factory() as store:
            reader = queries(store)
            ensure_patient(reader, patient_id)
            return reader.history(patient_id, parameter, minutes, limit)

    @app.get('/api/alerts', dependencies=[Depends(require_reader)])
    def alerts(patient_id: str | None = None, status: Literal['ACTIVE', 'RESOLVED', 'ALL'] = 'ACTIVE',
               severity: Literal['INFO', 'WARNING', 'CRITICAL', 'ALL'] = 'ALL',
               limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0, le=100000)):
        with store_factory() as store, store.transaction():
            store.connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            reader = queries(store)
            if patient_id is not None:
                ensure_patient(reader, patient_id)
            return reader.alerts(patient_id, status, severity, limit, offset)

    class ContactDoctorBody(BaseModel):
        model_config = ConfigDict(extra='forbid')
        doctor_id: UUID

    def resolve_without_receiver(alert_id, user):
        from src.repositories.postgres_repositories import PostgresAlertRepository
        from src.repositories.storage_codecs import alert_from_record
        with store_factory() as store, store.transaction():
            row = store.connection.execute(
                'SELECT alert_id,payload,status FROM alerts WHERE alert_id=%s FOR UPDATE', (alert_id,)).fetchone()
            if not row:
                raise AuthError(404, 'Alerte introuvable.')
            if row['status'] != 'ACTIVE':
                raise AuthError(409, 'Cette alerte est déjà résolue.')
            alert = alert_from_record(store.decode_payload('alerts', row['payload'], row['alert_id']))
            alert.resolve(reason='MANUAL_CLINICIAN')
            PostgresAlertRepository(store).save(alert)
            store.connection.execute('''INSERT INTO alert_actions
                (action_id,alert_id,actor_id,action) VALUES (%s,%s,%s,'RESOLVED')''',
                (uuid4(), alert_id, user['user_id']))
            AuditLog.record(store.connection, 'ALERT_RESOLVED', user['user_id'], alert_id)
        return alert

    @app.post('/api/alerts/{alert_id}/resolve', dependencies=[Depends(require_csrf)])
    def resolve_alert(alert_id: str, request: Request, user=Depends(current_user)):
        if user['role'] not in {'ADMIN', 'DOCTOR', 'NURSE'}:
            raise AuthError(403, 'Action réservée à l’équipe de soins.')
        result = None
        if receiver and hasattr(receiver, 'resolve_alert') and runtime().get('running'):
            result = receiver.resolve_alert(alert_id, user['user_id'])
            if result is None:
                raise AuthError(409, 'Cette alerte n’est plus active.')
        else:
            result = resolve_without_receiver(alert_id, user)
        return {'alert_id': result.alert_id, 'status': result.status,
                'resolved_at': result.resolved_at, 'resolution_reason': result.resolution_reason}

    @app.post('/api/alerts/{alert_id}/contact-doctor', status_code=201,
              dependencies=[Depends(require_csrf)])
    def contact_doctor(alert_id: str, body: ContactDoctorBody, request: Request,
                       user=Depends(current_user)):
        if user['role'] != 'NURSE':
            raise AuthError(403, 'Cette action est réservée aux infirmiers et infirmières.')
        with store_factory() as store, store.transaction():
            alert = store.connection.execute(
                "SELECT 1 FROM alerts WHERE alert_id=%s AND status='ACTIVE'", (alert_id,)).fetchone()
            doctor = store.connection.execute(
                "SELECT username FROM users WHERE user_id=%s AND role='DOCTOR' AND active AND approval_status='APPROVED'",
                (body.doctor_id,)).fetchone()
            if not alert:
                raise AuthError(409, 'Cette alerte n’est plus active.')
            if not doctor:
                raise AuthError(404, 'Médecin actif introuvable.')
            store.connection.execute('''INSERT INTO alert_actions
                (action_id,alert_id,actor_id,action,target_user_id)
                VALUES (%s,%s,%s,'DOCTOR_CONTACTED',%s)''',
                (uuid4(), alert_id, user['user_id'], body.doctor_id))
            AuditLog.record(store.connection, 'DOCTOR_CONTACTED', user['user_id'], alert_id)
        return {'alert_id': alert_id, 'doctor': doctor['username'], 'status': 'CONTACTED'}

    @app.get('/api/patients/{patient_id}/events', dependencies=[Depends(require_reader)])
    def events(patient_id: str, limit: int = Query(10, ge=1, le=100)):
        with store_factory() as store:
            reader = queries(store)
            ensure_patient(reader, patient_id)
            return {'items': reader.events(patient_id, limit)}

    @app.get('/', dependencies=[Depends(require_reader)])
    def index():
        return FileResponse(STATIC / 'index.html')

    @app.get('/alerts', dependencies=[Depends(require_reader)])
    def alerts_page():
        return FileResponse(STATIC / 'alerts.html')

    @app.get('/audit', dependencies=[Depends(require_reader)])
    def audit_page():
        return FileResponse(STATIC / 'audit.html')

    @app.get('/login')
    def login_page():
        return FileResponse(STATIC / 'login.html')

    @app.get('/signup')
    def signup_page():
        return FileResponse(STATIC / 'signup.html')

    @app.get('/admin', dependencies=[Depends(require_admin)])
    def admin_page():
        return FileResponse(STATIC / 'admin.html')

    @app.get('/assets/{filename}')
    def asset(filename: str):
        # HTML screens must only be served by their authenticated routes above.
        if filename not in {'style.css','security.css','auth.js','login.js','signup.js','app.js','admin.js','audit.js'}:
            raise HTTPException(404, 'Ressource introuvable')
        return FileResponse(STATIC / filename)
    return app
