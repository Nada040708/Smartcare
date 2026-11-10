"""HTTP authentication and role checks, independent of dashboard presentation."""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, Query
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from typing import Literal

from src.security.authentication import AuthError, AuthorizationService, csrf_token
from src.repositories.consent_repository import ConsentRepository

COOKIE = 'smartcare_session'


def current_user(request: Request):
    return request.app.state.auth.authenticate(request.cookies.get(COOKIE))


def require_reader(request: Request, user=Depends(current_user)):
    if not AuthorizationService.check_permission(user, 'read'):
        request.app.state.auth.audit('ACCESS_DENIED', user, 'dashboard')
        raise AuthError(403, 'Accès refusé.')
    return user


def require_admin(request: Request, user=Depends(current_user)):
    if not AuthorizationService.check_permission(user, 'admin'):
        request.app.state.auth.audit('ACCESS_DENIED', user, 'administration')
        raise AuthError(403, 'Droits administrateur requis.')
    return user


def check_origin(request):
    expected = str(request.base_url).rstrip('/')
    if request.headers.get('origin') != expected:
        raise AuthError(403, 'Origine de la requête refusée.')


def require_csrf(request: Request, user=Depends(current_user)):
    check_origin(request)
    token = request.cookies.get(COOKIE, '')
    if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), csrf_token(token)):
        request.app.state.auth.audit('CSRF_REJECTED', user)
        raise AuthError(403, 'Rechargez la page avant de réessayer.')
    return user


class LoginBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)


class CreateUserBody(LoginBody):
    role: Literal['ADMIN', 'DOCTOR', 'NURSE']


class RegistrationBody(LoginBody):
    role: Literal['DOCTOR', 'NURSE']


class UpdateUserBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['ADMIN', 'DOCTOR', 'NURSE'] | None = None
    active: StrictBool | None = None
    password: SecretStr | None = Field(default=None, min_length=12, max_length=128)


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    granted: StrictBool


class CreatePatientBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    patient_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    name: str = Field(min_length=1, max_length=120)
    profiles: list[Literal['diabetes', 'hypertension', 'anxiety']] = Field(min_length=1, max_length=3)
    monitoring_enabled: StrictBool = True


def security_router():
    router = APIRouter()

    @router.post('/api/auth/login')
    def login(body: LoginBody, request: Request, response: Response):
        check_origin(request)
        user, token = request.app.state.auth.login(body.username, body.password.get_secret_value(),
            request.client.host if request.client else 'unknown', request.cookies.get(COOKIE))
        response.set_cookie(COOKIE, token, max_age=8*3600, httponly=True,
                            secure=request.app.state.secure_cookies, samesite='strict', path='/')
        return {'user': user, 'csrf_token': csrf_token(token)}

    @router.post('/api/auth/signup', status_code=201)
    def signup(body: RegistrationBody, request: Request):
        check_origin(request)
        user = request.app.state.auth.request_registration(
            body.username, body.password.get_secret_value(), body.role)
        return {'user': user, 'message': "Demande envoyée. Un administrateur doit valider le compte avant la première connexion."}

    @router.get('/api/auth/me')
    def me(request: Request, user=Depends(current_user)):
        return {'user': user, 'csrf_token': csrf_token(request.cookies[COOKIE])}

    @router.post('/api/auth/logout', dependencies=[Depends(require_csrf)])
    def logout(request: Request, response: Response, user=Depends(current_user)):
        request.app.state.auth.logout(request.cookies[COOKIE], user)
        response.delete_cookie(COOKIE, httponly=True, secure=request.app.state.secure_cookies, samesite='strict')
        return {'ok': True}

    @router.get('/api/admin/users', dependencies=[Depends(require_admin)])
    def users(request: Request):
        return {'items': request.app.state.auth.list_users()}

    @router.get('/api/doctors', dependencies=[Depends(require_reader)])
    def doctors(request: Request):
        return {'items': request.app.state.auth.list_doctors()}

    @router.post('/api/admin/users', status_code=201, dependencies=[Depends(require_csrf)])
    def create_user(body: CreateUserBody, request: Request, user=Depends(require_admin)):
        return request.app.state.auth.create_user(body.username, body.password.get_secret_value(), body.role, user)

    @router.patch('/api/admin/users/{user_id}', dependencies=[Depends(require_csrf)])
    def update_user(user_id: UUID, body: UpdateUserBody, request: Request, user=Depends(require_admin)):
        changes = body.model_dump(exclude_unset=True)
        if not changes or any(value is None for value in changes.values()):
            raise AuthError(422, 'Indiquez au moins une modification valide.')
        if 'password' in changes:
            changes['password'] = body.password.get_secret_value()
        return request.app.state.auth.update_user(user_id, changes, user)

    @router.get('/api/admin/audit', dependencies=[Depends(require_admin)])
    def audit(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000)):
        return {'items': request.app.state.auth.list_audit(limit, offset)}

    @router.get('/api/admin/consents', dependencies=[Depends(require_admin)])
    def consents(request: Request):
        from .queries import DashboardQueries
        with request.app.state.store_factory() as store:
            patients = request.app.state.patients
            repo = ConsentRepository(store)
            return {'items':[dict(repo.get(pid,patients.get(pid)),name=patients[pid].name if pid in patients else pid)
                             for pid in sorted(DashboardQueries(store,patients).known_ids())]}

    @router.put('/api/admin/consents/{patient_id}', dependencies=[Depends(require_csrf)])
    def consent(patient_id: str, body: ConsentBody, request: Request, user=Depends(require_admin)):
        from .queries import DashboardQueries
        with request.app.state.store_factory() as store:
            if patient_id not in DashboardQueries(store,request.app.state.patients).known_ids():
                raise AuthError(404,'Patient introuvable.')
            return ConsentRepository(store).set(patient_id,body.granted,user)

    @router.get('/api/patient-registry', dependencies=[Depends(require_reader)])
    def patient_registry(request: Request):
        from .patients import profile_catalog
        return {'profiles': profile_catalog(), 'can_create': current_user(request)['role'] in {'ADMIN','DOCTOR'}}

    @router.post('/api/patient-registry', status_code=201, dependencies=[Depends(require_csrf)])
    def create_patient(body: CreatePatientBody, request: Request, user=Depends(current_user)):
        if user['role'] not in {'ADMIN', 'DOCTOR'} or not user['active']:
            request.app.state.auth.audit('ACCESS_DENIED', user, 'patient-registry')
            raise AuthError(403, 'Seuls un médecin ou un administrateur peut ajouter un patient.')
        profiles = list(dict.fromkeys(body.profiles))
        name = body.name.strip()
        if not name:
            raise AuthError(422, 'Le nom du patient est requis.')
        if body.patient_id in request.app.state.patients:
            raise AuthError(409, 'Cet identifiant patient existe déjà.')
        from psycopg.errors import UniqueViolation
        from .patients import patient_from_record
        with request.app.state.store_factory() as store, store.transaction():
            try:
                record = store.connection.execute('''INSERT INTO patient_registry
                    (patient_id,name,profiles,monitoring_enabled,created_by)
                    VALUES (%s,%s,%s,%s,%s) RETURNING patient_id,name,profiles,monitoring_enabled''',
                    (body.patient_id, name, profiles, body.monitoring_enabled, user['user_id'])).fetchone()
            except UniqueViolation:
                raise AuthError(409, 'Cet identifiant patient existe déjà.') from None
            from src.security.authentication import AuditLog
            AuditLog.record(store.connection, 'PATIENT_CREATED', user['user_id'], body.patient_id)
        patient = patient_from_record(record)
        request.app.state.patients[patient.patient_id] = patient
        return {'patient_id': patient.patient_id, 'name': patient.name,
                'profiles': [profile.profile_id for profile in patient.profiles],
                'monitoring_enabled': patient.monitoring_enabled}

    return router
