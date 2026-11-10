"""MQTT credentials may only be used over a verified TLS channel."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import ssl


@dataclass(frozen=True)
class MQTTAuthentication:
    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class TLSService:
    ca_file: str
    authentication: MQTTAuthentication

    @classmethod
    def from_file(cls, path):
        path = Path(path).resolve()
        data = json.loads(path.read_text())
        if set(data) != {'ca_file', 'username', 'password'} or not all(isinstance(v, str) and v for v in data.values()):
            raise ValueError('MQTT configuration requires ca_file, username and password')
        ca = (path.parent / data['ca_file']).resolve()
        return cls(str(ca), MQTTAuthentication(data['username'], data['password']))

    def configure(self, client):
        context = ssl.create_default_context(cafile=self.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # create_default_context enforces both certificate chain and hostname verification.
        client.tls_set_context(context)
        client.username_pw_set(self.authentication.username, self.authentication.password)
