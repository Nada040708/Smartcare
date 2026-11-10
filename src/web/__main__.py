import argparse
from pathlib import Path
import uvicorn

from .app import create_app
from .patients import DEFAULT_PATIENTS, load_patients
from src.repositories.postgres_store import PostgresStore
from src.communication.tls import TLSService
from src.processing.connection_monitor import DEFAULT_POLICY, load_connection_policy


def main():
    parser = argparse.ArgumentParser(description='Smartcare — dashboard local multipatient')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db-schema', default='smartcare')
    parser.add_argument('--patients', default=str(DEFAULT_PATIENTS))
    parser.add_argument('--connection-policy', default=str(DEFAULT_POLICY), help='Capteurs et délais attendus')
    parser.add_argument('--broker', default='localhost')
    parser.add_argument('--mqtt-port', type=int)
    parser.add_argument('--mqtt-config', help='Fichier JSON privé contenant CA et identifiants MQTT')
    parser.add_argument('--tls-cert', default='.secrets/tls/web.crt')
    parser.add_argument('--tls-key', default='.secrets/tls/web.key')
    parser.add_argument('--allow-insecure-local', action='store_true', help='Ancienne démonstration locale HTTP/MQTT, explicitement non sécurisée')
    parser.add_argument('--no-ingest', action='store_true', help='Consulter les historiques sans recevoir MQTT')
    args = parser.parse_args()
    args.mqtt_port = args.mqtt_port or (1883 if args.allow_insecure_local else 8883)
    if not 1 <= args.port <= 65535 or not 1 <= args.mqtt_port <= 65535:
        parser.error('Les ports doivent être compris entre 1 et 65535')
    patients = load_patients(args.patients)
    connection_policy = load_connection_policy(args.connection_policy)
    if not args.allow_insecure_local:
        if not Path(args.tls_cert).is_file() or not Path(args.tls_key).is_file():
            parser.error('Certificats absents : exécutez scripts/setup_security.py (voir docs/step10_security.md).')
        if not args.no_ingest and not args.mqtt_config:
            args.mqtt_config = '.secrets/receiver.json'
    security = TLSService.from_file(args.mqtt_config) if args.mqtt_config else None
    # Initialize even in history-only mode; a missing DB is an explicit startup failure.
    with PostgresStore(schema=args.db_schema):
        pass
    app = create_app(schema=args.db_schema, patients=patients, ingest=not args.no_ingest,
                     broker=args.broker, port=args.mqtt_port, mqtt_security=security,
                     secure_cookies=not args.allow_insecure_local, connection_policy=connection_policy)
    uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1, proxy_headers=False,
                ssl_certfile=None if args.allow_insecure_local else args.tls_cert,
                ssl_keyfile=None if args.allow_insecure_local else args.tls_key)


if __name__ == '__main__':
    main()
