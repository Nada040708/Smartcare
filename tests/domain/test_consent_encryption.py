import pytest
from cryptography.fernet import Fernet
from src.domain.consent import Consent
from src.security.encryption import EncryptionService, EncryptionError


def test_consent_revocation_and_type_validation():
    c=Consent('P001',True);c.revoke();assert not c.granted
    with pytest.raises(ValueError):Consent('P001','true')


def test_encryption_authenticates_context_and_tampering_and_uses_random_tokens():
    service=EncryptionService(Fernet.generate_key())
    data={'value':84,'measurement_id':'M1'}
    first=service.encrypt(data,'schema:measurements')
    assert first!=service.encrypt(data,'schema:measurements')
    assert service.decrypt(first,'schema:measurements',identity='M1',identity_field='measurement_id')==data
    with pytest.raises(EncryptionError):service.decrypt(first,'other:measurements')
    with pytest.raises(EncryptionError):service.decrypt({'encrypted':'fernet-v1','token':'broken'},'schema:measurements')


def test_key_generation_never_replaces_an_existing_key(tmp_path):
    path=tmp_path/'storage.key';EncryptionService.create_key(path);before=path.read_bytes()
    with pytest.raises(FileExistsError):EncryptionService.create_key(path)
    assert path.read_bytes()==before
