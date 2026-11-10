"""Generate local-only certificates and random MQTT credentials; never overwrite secrets."""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]


def write(path, value, mode=0o600):
    with path.open('xb') as stream:
        os.chmod(path, mode)
        stream.write(value.encode() if isinstance(value, str) else value)


def certificates(directory):
    directory.mkdir(mode=0o755)
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Smartcare local development CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
          .not_valid_after(now+timedelta(days=365)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, None, None), True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False)
          .sign(ca_key, hashes.SHA256()))
    write(directory/'ca.crt', ca.public_bytes(serialization.Encoding.PEM), 0o644)
    write(directory/'ca.key', ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()))
    for service, names in [('web', ['localhost']), ('broker', ['localhost', 'mosquitto'])]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca.subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
                .not_valid_after(now+timedelta(days=90)).add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False)
                .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, None, None), True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names] +
                    [x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
                .sign(ca_key, hashes.SHA256()))
        write(directory/f'{service}.crt', cert.public_bytes(serialization.Encoding.PEM), 0o644)
        # Broker key must be readable by its unprivileged container UID; host parent is 0700.
        write(directory/f'{service}.key', key.private_bytes(serialization.Encoding.PEM,
              serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), 0o644 if service=='broker' else 0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.secrets')
    args = parser.parse_args()
    directory = args.output.resolve()
    if directory.exists():
        parser.error('Le dossier existe déjà : aucune clé ni aucun identifiant ne sera remplacé.')
    os.umask(0o077)
    directory.mkdir(mode=0o700)
    write(directory/'storage.key',Fernet.generate_key())
    certificates(directory/'tls')
    (directory/'broker').mkdir(mode=0o755)
    os.chmod(directory/'broker', 0o755)
    os.chmod(directory/'tls', 0o755)
    passwords = {name: secrets.token_urlsafe(32) for name in ['simulator', 'node-red', 'receiver', 'healthcheck']}
    for name in ['simulator', 'receiver', 'node-red']:
        write(directory/f'{name}.json', json.dumps(dict(ca_file='tls/ca.crt', username=name, password=passwords[name])),
              0o644 if name=='node-red' else 0o600)
    # Conversion is done using the exact Mosquitto version used by Compose, in ephemeral memory.
    result = subprocess.run(['docker', 'run', '--rm', '-i', '--entrypoint', '/bin/sh', 'eclipse-mosquitto:2.0',
        '-c', 'umask 077; cat > /tmp/passwords; mosquitto_passwd -U /tmp/passwords; cat /tmp/passwords'],
        input=''.join(f'{name}:{password}\n' for name,password in passwords.items()),
        text=True, capture_output=True, check=True)
    write(directory/'broker/passwords', result.stdout, 0o644)
    write(directory/'broker/healthcheck.password', passwords['healthcheck'], 0o644)
    print(f'Certificats et identifiants générés dans {directory}. Aucun secret affiché.')
    print('Certificats serveur : 90 jours. CA locale : 365 jours. Voir docs/step10_security.md.')


if __name__ == '__main__':
    main()
