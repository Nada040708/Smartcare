"""Explicit local demonstration bootstrap. Never changes an existing account."""
from .authentication import AuthenticationService, AuthError


def initialize_demo_admin(store_factory, *, local_demo=False, password=None, prompt=None):
    if not local_demo:
        return False
    service = AuthenticationService(store_factory)
    if service.list_users():
        return False
    password = password or (prompt() if prompt else None)
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('SMARTCARE_DEMO_ADMIN_PASSWORD doit contenir 12 à 128 caractères.')
    try:
        service.create_user('admin', password, 'ADMIN', bootstrap=True)
    except AuthError as error:
        # Another simultaneous startup may have won the existing bootstrap lock.
        if error.status == 409 and service.list_users():
            return False
        raise
    return True
