import json
from unittest.mock import Mock
import pytest

from src.communication.tls import TLSService, MQTTAuthentication


def test_mqtt_secret_is_not_in_repr_and_requires_complete_configuration(tmp_path):
    assert 'super-secret' not in repr(MQTTAuthentication('simulator','super-secret'))
    path=tmp_path/'config.json'
    path.write_text(json.dumps({'username':'simulator','password':'secret'}))
    with pytest.raises(ValueError):
        TLSService.from_file(path)
    path.write_text(json.dumps({'username':'simulator','password':'secret','ca_file':'ca.crt'}))
    config=TLSService.from_file(path)
    assert config.ca_file==str(tmp_path/'ca.crt')
    with pytest.raises(FileNotFoundError):
        config.configure(Mock())  # Missing CA must never fall back to clear text.
