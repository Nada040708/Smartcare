"""Run the complete dashboard browser scenario with disposable data and credentials."""
from pathlib import Path
import secrets
import sys
import threading
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from psycopg import sql
import uvicorn
from examples.step9_live import cycle_measurements
from scripts.check_dashboard_browser import main as check_dashboard
from src.processing.persistent_monitoring import PersistentMonitoring
from src.repositories.postgres_store import PostgresStore
from src.security.authentication import AuthenticationService
from src.web.app import create_app
from src.web.patients import load_patients


def main():
    schema='smartcare_browser_'+uuid4().hex
    factory=lambda:PostgresStore(schema=schema,initialize=False)
    password=secrets.token_urlsafe(24)
    patients=load_patients()
    server=None
    try:
        with PostgresStore(schema=schema) as store:
            pipeline=PersistentMonitoring(store)
            for cycle in (0,1,24):
                readings=cycle_measurements(patients,cycle)
                for patient in patients.values():
                    pipeline.process([m for m in readings if m.patient_id==patient.patient_id],patient)
                time.sleep(.05)
        AuthenticationService(factory).create_user('browser-admin',password,'ADMIN',bootstrap=True)
        app=create_app(ingest=False,patients=patients,store_factory=factory)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8443,log_level='warning',
            proxy_headers=False,ssl_certfile=str(ROOT/'.secrets/tls/web.crt'),ssl_keyfile=str(ROOT/'.secrets/tls/web.key')))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.05)
        assert server.started,'Port 8443 must be free'
        check_dashboard(['--url','https://127.0.0.1:8443','--username','browser-admin','--local-test-ca'],password=password)
    finally:
        if server:
            server.should_exit=True;thread.join(timeout=12)
        with PostgresStore(schema=schema) as store:
            store.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':main()
