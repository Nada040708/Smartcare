"""One local demo entry point, reusing the production pipeline and security services."""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import json
import math
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

from cryptography import x509
from dotenv import load_dotenv, set_key
from psycopg import Error as DatabaseError
from src.security.authentication import AuthError
from src.security.encryption import EncryptionError

ROOT = Path(__file__).resolve().parents[1]


def private_database_password():
    """Generate a local database password once; never keep a repository default."""
    value = os.getenv('POSTGRES_PASSWORD')
    if value:
        if len(value) < 16:
            raise ValueError('POSTGRES_PASSWORD doit contenir au moins 16 caractères.')
        return value
    path = ROOT/'.env'
    if not path.exists():
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    value = secrets.token_urlsafe(32)
    set_key(str(path), 'POSTGRES_PASSWORD', value)
    os.chmod(path, 0o600)
    os.environ['POSTGRES_PASSWORD'] = value
    print('Secret PostgreSQL local généré dans .env privé (ignoré par Git).')
    return value


def compose(project, *, editor=False):
    command = ['docker', 'compose', '-p', project, '-f', str(ROOT/'compose.yaml'),
               '-f', str(ROOT/'compose.secure.yaml')]
    if editor:
        command += ['-f', str(ROOT/'compose.demo.yaml')]
    return command


def private_password():
    value = os.getenv('SMARTCARE_DEMO_ADMIN_PASSWORD')
    if not value:
        if not sys.stdin.isatty():
            raise ValueError('Définissez SMARTCARE_DEMO_ADMIN_PASSWORD dans .env (12 à 128 caractères).')
        value = getpass('Choisissez le mot de passe admin de démonstration (12–128 caractères) : ')
        if not 12 <= len(value) <= 128:
            raise ValueError('Mot de passe invalide : 12 à 128 caractères requis.')
        path = ROOT/'.env'
        if not path.exists():
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        set_key(str(path), 'SMARTCARE_DEMO_ADMIN_PASSWORD', value)
        os.chmod(path, 0o600)
        os.environ['SMARTCARE_DEMO_ADMIN_PASSWORD'] = value
        print('Mot de passe enregistré dans .env privé (ignoré par Git), sans affichage.')
    if not 12 <= len(value) <= 128:
        raise ValueError('SMARTCARE_DEMO_ADMIN_PASSWORD doit contenir 12 à 128 caractères.')
    return value


def prepare_secrets(directory):
    if not directory.exists():
        subprocess.run([sys.executable, str(ROOT/'scripts/setup_security.py'), '--output', str(directory)], check=True)
    required = ['storage.key', 'simulator.json', 'receiver.json', 'node-red.json',
                'broker/passwords', 'broker/healthcheck.password', 'tls/ca.crt',
                'tls/web.crt', 'tls/web.key', 'tls/broker.crt', 'tls/broker.key']
    if any(not (directory/name).is_file() for name in required):
        raise ValueError('Installation privée incomplète : restaurez les fichiers manquants. Aucune clé existante ne sera remplacée.')
    for name in ['ca', 'web', 'broker']:
        certificate = x509.load_pem_x509_certificate((directory/f'tls/{name}.crt').read_bytes())
        now = datetime.now(timezone.utc)
        if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc:
            raise ValueError('Certificat expiré ou horloge incorrecte. Voir docs/SECURITE_ET_TESTS.md ; ne supprimez pas .secrets.')


def prepare_editor(directory):
    path = directory/'editor.json'
    if path.exists():
        return
    password = private_password()
    # Password only on stdin; no shell, argument, log or persisted clear-text editor credential.
    result = subprocess.run(['docker', 'run', '--rm', '-i', '--entrypoint', 'node',
        'nodered/node-red:4.1.15-22', '-e',
        "let s='';process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>process.stdout.write(require('bcryptjs').hashSync(s,12)))"],
        input=password, text=True, capture_output=True, check=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump({'username':'admin', 'password':result.stdout, 'permissions':'read'}, stream)
    # Readable by the container UID inside the host's private 0700 directory.
    os.chmod(path, 0o644)


def scenario_readings(patients, cycle, scenario, *, elapsed=0, timeout=10):
    from examples.step9_live import cycle_measurements
    readings = cycle_measurements(patients, cycle, 'normal')
    if scenario == 'disconnection' and 15 <= elapsed < 15+timeout+5:
        readings = [m for m in readings if m.patient_id != 'P001']
    if scenario == 'anomaly':
        for m in readings:
            if m.patient_id == 'P001' and m.parameter == 'glucose':
                m.value = 240  # Synthetic input, evaluated by the configured diabetes rule.
    return readings


def simulate(args):
    from src.communication import MQTTPublisher
    from src.communication.tls import TLSService
    from src.processing.connection_monitor import load_connection_policy
    from src.web.patients import load_patients
    patients = load_patients()
    timeout = load_connection_policy()['timeout_seconds']
    if not math.isfinite(args.duration) or args.duration <= 0:
        raise ValueError('La durée doit être positive.')
    print(f'SIMULATION · {args.scenario} · durée {args.duration:g} s · arrêt : Ctrl+C', flush=True)
    if args.scenario == 'disconnection':
        print(f'P001 émet 15 s, se tait {timeout+5:g} s, puis reprend. P002/P003 continuent.', flush=True)
    start = time.monotonic(); cycle = 0; last_phase = None
    with MQTTPublisher(port=8883, security=TLSService.from_file(ROOT/'.secrets/simulator.json')) as publisher:
        while time.monotonic()-start < args.duration:
            elapsed = time.monotonic()-start
            phase = 'silence P001' if args.scenario == 'disconnection' and 15 <= elapsed < 20+timeout else args.scenario
            if phase != last_phase:
                print(f'{elapsed:.0f} s : {phase}', flush=True); last_phase = phase
            for reading in scenario_readings(patients, cycle, args.scenario, elapsed=elapsed, timeout=timeout):
                publisher.publish(reading)
            cycle += 1
            time.sleep(1)


def main(argv=None):
    os.chdir(ROOT)
    load_dotenv(ROOT/'.env', override=False)
    parser = argparse.ArgumentParser(description='Smartcare : démonstration locale avec HTTPS et MQTT/TLS.')
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('start-demo', help='Préparer puis lancer la démonstration locale explicite')
    start.add_argument('--node-red', action='store_true', help='Montrer le flow dans un éditeur HTTPS local en lecture seule')
    start.add_argument('--db-schema', default='smartcare')
    start.add_argument('--port', type=int, default=8000)
    start.add_argument('--project', default='smartcare')
    simulation = commands.add_parser('simulate', help='Émettre de vraies mesures MQTT de simulation')
    simulation.add_argument('scenario', choices=['normal', 'anomaly', 'disconnection'])
    simulation.add_argument('--duration', type=float, default=60)
    stop = commands.add_parser('stop', help='Arrêter les conteneurs sans supprimer les volumes')
    stop.add_argument('--project', default='smartcare')
    args = parser.parse_args(argv)
    try:
        if args.command == 'simulate':
            simulate(args); return
        if args.command == 'stop':
            subprocess.run(compose(args.project)+['stop'], check=True); return
        if not 1 <= args.port <= 65535:
            raise ValueError('Port invalide.')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', args.port))
        private_database_password()
        subprocess.run(['docker','info'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        prepare_secrets(ROOT/'.secrets')
        if args.node_red:
            prepare_editor(ROOT/'.secrets')
        subprocess.run(compose(args.project, editor=args.node_red)+['up','-d','--wait'], check=True)
        from src.repositories.postgres_store import PostgresStore
        from src.security.demo import initialize_demo_admin
        from src.web.app import create_app
        from src.communication.tls import TLSService
        import uvicorn
        with PostgresStore(schema=args.db_schema):
            pass
        factory = lambda: PostgresStore(schema=args.db_schema, initialize=False)
        created = initialize_demo_admin(factory, local_demo=True,
            password=os.getenv('SMARTCARE_DEMO_ADMIN_PASSWORD'), prompt=private_password)
        print('Compte admin créé.' if created else 'Comptes existants conservés : utilisez leurs identifiants habituels.')
        print(f'Dashboard : https://127.0.0.1:{args.port}/login · arrêt du serveur : Ctrl+C', flush=True)
        if args.node_red:
            print('Flow Node-RED : https://127.0.0.1:1880 · admin · mot de passe choisi lors de sa première préparation.', flush=True)
        app = create_app(schema=args.db_schema, port=8883, demo_mode=True,
            mqtt_security=TLSService.from_file(ROOT/'.secrets/receiver.json'))
        uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1, proxy_headers=False,
            ssl_certfile=str(ROOT/'.secrets/tls/web.crt'), ssl_keyfile=str(ROOT/'.secrets/tls/web.key'))
    except KeyboardInterrupt:
        print('\nArrêt demandé. Les historiques sont conservés.')
    except DatabaseError:
        parser.exit(1, 'PostgreSQL indisponible ou configuration incohérente : vérifiez .env et les services. Aucun historique réinitialisé.\n')
    except (EncryptionError, AuthError, RuntimeError) as error:
        parser.exit(1, f'Démarrage interrompu : {error}\n')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            parser.exit(1, 'Service indisponible : vérifiez Docker Desktop et les ports. Aucun volume supprimé.\n')
        parser.exit(1, f'{error}\n')
