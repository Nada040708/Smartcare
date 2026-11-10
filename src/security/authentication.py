"""Opaque, revocable sessions. Passwords and session tokens are never stored in clear."""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from psycopg.errors import UniqueViolation

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
ROLES = {'ADMIN', 'DOCTOR', 'NURSE'}


class AuthError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token):
    return digest('csrf:' + token)


def public_user(row):
    keys = ('user_id', 'username', 'role', 'active', 'approval_status', 'requested_at')
    return {key: str(row[key]) if key == 'user_id' else row[key]
            for key in keys if key in row}


def normalize_username(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,63}', value):
        raise AuthError(422, 'Identifiant : 3 à 64 caractères (lettres, chiffres, point, tiret).')
    return value


def password_hash(password):
    if not 12 <= len(password) <= 128:
        raise AuthError(422, 'Le mot de passe doit contenir entre 12 et 128 caractères.')
    return HASHER.hash(password)


class AuditLog:
    @staticmethod
    def record(connection, action, user_id=None, target=None):
        # Deliberately exclude passwords, cookies, IP addresses and medical readings.
        connection.execute('INSERT INTO audit_logs (user_id,action,target) VALUES (%s,%s,%s)',
                           (user_id, action, target))


class AuthorizationService:
    PERMISSIONS = {'ADMIN': {'read', 'admin'}, 'DOCTOR': {'read'}, 'NURSE': {'read'}}

    @classmethod
    def check_permission(cls, user, permission):
        return bool(user['active'] and permission in cls.PERMISSIONS.get(user['role'], set()))


class AuthenticationService:
    def __init__(self, store_factory):
        self.store_factory = store_factory

    @staticmethod
    def _lock(store):
        # Serialize account and session mutations within this prototype's schema.
        store.connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',
                                 (store.schema + ':authentication',))

    @staticmethod
    def _assert_admin(db, actor):
        # Recheck inside the mutation transaction: an in-flight request can outlive revocation.
        row = db.execute('SELECT role,active FROM users WHERE user_id=%s',
                         (actor['user_id'],)).fetchone() if actor else None
        if not row or not AuthorizationService.check_permission(row, 'admin'):
            raise AuthError(403, 'Droits administrateur requis.')

    def login(self, username, password, address, previous_token=None):
        username = username.strip().lower()
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        error = None
        with self.store_factory() as store, store.transaction():
            self._lock(store)
            db = store.connection
            db.execute('DELETE FROM auth_throttle WHERE expires_at <= %s', (now,))
            db.execute("DELETE FROM auth_sessions WHERE expires_at <= %s OR last_seen_at <= %s",
                       (now, now - timedelta(minutes=30)))
            buckets = [(digest('user:' + username), 10), (digest('ip:' + address), 50)]
            blocked = False
            for bucket, limit in buckets:
                row = db.execute('SELECT attempts FROM auth_throttle WHERE bucket=%s', (bucket,)).fetchone()
                blocked |= bool(row and row['attempts'] >= limit)
            if blocked:
                AuditLog.record(db, 'LOGIN_THROTTLED')
                error = AuthError(429, 'Trop de tentatives. Réessayez dans cinq minutes.')
            else:
                row = db.execute('SELECT * FROM users WHERE username=%s', (username,)).fetchone()
                try:
                    good = HASHER.verify(row['password_hash'] if row else DUMMY_HASH, password)
                except (VerificationError, InvalidHashError):
                    good = False
                if not row or not row['active'] or not good:
                    for bucket, _ in buckets:
                        db.execute('''INSERT INTO auth_throttle VALUES (%s,1,%s)
                                      ON CONFLICT (bucket) DO UPDATE SET attempts=auth_throttle.attempts+1''',
                                   (bucket, now + timedelta(minutes=5)))
                    AuditLog.record(db, 'LOGIN_FAILED')
                    error = AuthError(401, 'Identifiant ou mot de passe incorrect.')
                else:
                    db.execute('DELETE FROM auth_throttle WHERE bucket=%s', (buckets[0][0],))
                    if previous_token:
                        db.execute('DELETE FROM auth_sessions WHERE token_hash=%s', (digest(previous_token),))
                    if HASHER.check_needs_rehash(row['password_hash']):
                        db.execute('UPDATE users SET password_hash=%s WHERE user_id=%s',
                                   (HASHER.hash(password), row['user_id']))
                    db.execute('INSERT INTO auth_sessions (token_hash,user_id,expires_at) VALUES (%s,%s,%s)',
                               (digest(token), row['user_id'], now + timedelta(hours=8)))
                    AuditLog.record(db, 'LOGIN_SUCCESS', row['user_id'])
                    user = public_user(row)
        if error:
            raise error
        return user, token

    def authenticate(self, token):
        if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise AuthError(401, 'Connexion requise.')
        with self.store_factory() as store, store.transaction():
            row = store.connection.execute('''UPDATE auth_sessions s SET last_seen_at=now()
                FROM users u WHERE s.user_id=u.user_id AND s.token_hash=%s AND u.active
                AND s.expires_at>now() AND s.last_seen_at>now()-interval '30 minutes'
                RETURNING u.user_id,u.username,u.role,u.active''', (digest(token),)).fetchone()
        if not row:
            raise AuthError(401, 'Votre session a expiré. Reconnectez-vous.')
        return public_user(row)

    def logout(self, token, user):
        with self.store_factory() as store, store.transaction():
            store.connection.execute('DELETE FROM auth_sessions WHERE token_hash=%s', (digest(token),))
            AuditLog.record(store.connection, 'LOGOUT', user['user_id'])

    def audit(self, action, user=None, target=None):
        with self.store_factory() as store:
            AuditLog.record(store.connection, action, user['user_id'] if user else None, target)

    def create_user(self, username, password, role, actor=None, *, bootstrap=False):
        username = normalize_username(username)
        if role not in ROLES:
            raise AuthError(422, 'Rôle inconnu.')
        hashed = password_hash(password)
        with self.store_factory() as store, store.transaction():
            self._lock(store)
            db = store.connection
            if bootstrap:
                if role != 'ADMIN' or db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                    raise AuthError(409, 'Un compte existe déjà. Utilisez la gestion des utilisateurs.')
            else:
                self._assert_admin(db, actor)
            try:
                row = db.execute('''INSERT INTO users(user_id,username,password_hash,role)
                                    VALUES (%s,%s,%s,%s) RETURNING *''',
                                 (uuid4(), username, hashed, role)).fetchone()
            except UniqueViolation:
                raise AuthError(409, 'Cet identifiant est déjà utilisé.') from None
            AuditLog.record(db, 'BOOTSTRAP_ADMIN' if bootstrap else 'USER_CREATED',
                            row['user_id'] if bootstrap else actor['user_id'], str(row['user_id']))
            return public_user(row)

    def request_registration(self, username, password, role):
        """Create a disabled clinician account awaiting explicit admin approval."""
        username = normalize_username(username)
        if role not in {'DOCTOR', 'NURSE'}:
            raise AuthError(422, 'Seuls les médecins et infirmiers peuvent demander un compte.')
        hashed = password_hash(password)
        with self.store_factory() as store, store.transaction():
            self._lock(store)
            db = store.connection
            try:
                row = db.execute('''INSERT INTO users
                    (user_id,username,password_hash,role,active,approval_status)
                    VALUES (%s,%s,%s,%s,FALSE,'PENDING') RETURNING *''',
                    (uuid4(), username, hashed, role)).fetchone()
            except UniqueViolation:
                raise AuthError(409, 'Cet identifiant est déjà utilisé.') from None
            AuditLog.record(db, 'REGISTRATION_REQUESTED', row['user_id'], str(row['user_id']))
            return public_user(row)

    def update_user(self, user_id, changes, actor):
        if not AuthorizationService.check_permission(actor, 'admin'):
            raise AuthError(403, 'Droits administrateur requis.')
        hashed = password_hash(changes['password']) if changes.get('password') is not None else None
        with self.store_factory() as store, store.transaction():
            self._lock(store)
            db = store.connection
            self._assert_admin(db, actor)
            row = db.execute('SELECT * FROM users WHERE user_id=%s', (user_id,)).fetchone()
            if not row:
                raise AuthError(404, 'Utilisateur introuvable.')
            role, active = changes.get('role', row['role']), changes.get('active', row['active'])
            if role not in ROLES or not isinstance(active, bool):
                raise AuthError(422, 'Rôle ou état invalide.')
            if row['role'] == 'ADMIN' and row['active'] and (role != 'ADMIN' or not active):
                count = db.execute("SELECT count(*) AS n FROM users WHERE role='ADMIN' AND active").fetchone()['n']
                if count <= 1:
                    raise AuthError(409, 'Conservez au moins un administrateur actif.')
            approval = 'APPROVED' if active else row.get('approval_status', 'APPROVED')
            result = db.execute('''UPDATE users SET role=%s,active=%s,password_hash=%s,
                                   approval_status=%s,approved_at=CASE WHEN %s='APPROVED' THEN COALESCE(approved_at,now()) ELSE approved_at END
                                   WHERE user_id=%s RETURNING *''',
                                (role, active, hashed or row['password_hash'], approval, approval, user_id)).fetchone()
            db.execute('DELETE FROM auth_sessions WHERE user_id=%s', (user_id,))
            action = 'REGISTRATION_APPROVED' if row.get('approval_status') == 'PENDING' and active else 'USER_UPDATED'
            AuditLog.record(db, action, actor['user_id'], str(user_id))
            return public_user(result)

    def list_users(self):
        with self.store_factory() as store:
            return [public_user(row) for row in store.connection.execute(
                "SELECT user_id,username,role,active,approval_status,requested_at FROM users ORDER BY approval_status DESC,username")]

    def list_doctors(self):
        with self.store_factory() as store:
            return [public_user(row) for row in store.connection.execute(
                "SELECT user_id,username,role,active,approval_status,requested_at FROM users "
                "WHERE role='DOCTOR' AND active AND approval_status='APPROVED' ORDER BY username")]

    def list_audit(self, limit=50, offset=0):
        with self.store_factory() as store:
            return store.connection.execute('''SELECT a.log_id,a.timestamp,a.action,a.target,u.username
                FROM audit_logs a LEFT JOIN users u ON u.user_id=a.user_id
                ORDER BY a.timestamp DESC,a.log_id DESC LIMIT %s OFFSET %s''', (limit, offset)).fetchall()
