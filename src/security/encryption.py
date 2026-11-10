"""Authenticated encryption of clinical payloads, using a private local key."""
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_KEY = Path(__file__).resolve().parents[2]/'.secrets/storage.key'


class EncryptionError(RuntimeError):
    pass


class EncryptionService:
    def __init__(self, key):
        try:
            self._cipher = Fernet(key)
        except (ValueError, TypeError):
            raise EncryptionError('Invalid storage encryption key') from None

    @classmethod
    def from_file(cls, path=None):
        path = Path(path or os.getenv('SMARTCARE_STORAGE_KEY_FILE', str(DEFAULT_KEY)))
        try:
            key = path.read_bytes().strip()
        except OSError:
            raise EncryptionError('Storage key unavailable; run python -m src.security storage-key') from None
        return cls(key)

    @staticmethod
    def create_key(path=DEFAULT_KEY):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Never replace an existing key: old records would become unreadable.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(Fernet.generate_key())

    def encrypt(self, record, context):
        raw = json.dumps({'context':context,'record':record}, ensure_ascii=False, allow_nan=False).encode()
        return {'encrypted':'fernet-v1','token':self._cipher.encrypt(raw).decode('ascii')}

    def decrypt(self, envelope, context, *, identity=None, identity_field=None):
        try:
            if not isinstance(envelope, dict) or set(envelope) != {'encrypted','token'} or envelope['encrypted'] != 'fernet-v1':
                raise ValueError('Invalid envelope')
            data = json.loads(self._cipher.decrypt(envelope['token']))
            if data['context'] != context or (identity_field and data['record'][identity_field] != identity):
                raise ValueError('Wrong record context')
            return data['record']
        except (InvalidToken, ValueError, KeyError, TypeError):
            raise EncryptionError('Stored clinical data cannot be decrypted or verified') from None
