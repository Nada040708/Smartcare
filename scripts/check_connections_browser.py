"""Live TLS → Node-RED → PostgreSQL → HTTPS checks for silence and partial data."""
from pathlib import Path
import secrets
import re
import sys
import threading
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from playwright.sync_api import sync_playwright,expect
from psycopg import sql
import uvicorn

from examples.step9_live import cycle_measurements
from src.communication import MQTTPublisher
from src.communication.tls import TLSService
from src.domain import Patient
from src.domain.consent import Consent
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.repositories.postgres_store import PostgresStore
from src.security.authentication import AuthenticationService
from src.web.app import create_app


def main():
    schema='smartcare_browser_'+uuid4().hex
    factory=lambda:PostgresStore(schema=schema,initialize=False)
    first,second='BC1_'+uuid4().hex[:6],'BC2_'+uuid4().hex[:6]
    patients={first:Patient(first,'Patient panne',consent=Consent(first,True)),second:Patient(second,'Patient témoin',consent=Consent(second,True))}
    policy={'timeout_seconds':4,'startup_grace_seconds':8,'devices':[
        {'patient_id':pid,'device_id':'SIM_'+pid,'parameters':list(PARAMETER_DEFINITIONS)} for pid in patients]}
    password=secrets.token_urlsafe(24)
    stop=threading.Event();phase=['normal'];errors=[]
    server=None;publisher_thread=None
    url='https://127.0.0.1:8443'
    def publish():
        try:
            with MQTTPublisher(port=8883,security=TLSService.from_file(ROOT/'.secrets/simulator.json')) as publisher:
                cycle=0
                while not stop.is_set():
                    for m in cycle_measurements(patients,cycle,'normal'):
                        if m.patient_id==first and (phase[0]=='silence' or (phase[0]=='missing' and m.parameter=='glucose')):
                            continue
                        publisher.publish(m)
                    cycle+=1
                    stop.wait(.4)
        except Exception as error:
            errors.append(type(error).__name__)
    try:
        with PostgresStore(schema=schema):
            pass
        auth=AuthenticationService(factory)
        admin=auth.create_user('test-admin',password,'ADMIN',bootstrap=True)
        auth.create_user('test-doctor',password,'DOCTOR',admin)
        app=create_app(schema=schema,patients=patients,store_factory=factory,port=8883,
            mqtt_security=TLSService.from_file(ROOT/'.secrets/receiver.json'),connection_policy=policy)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8443,log_level='warning',
            ssl_certfile=str(ROOT/'.secrets/tls/web.crt'),ssl_keyfile=str(ROOT/'.secrets/tls/web.key'),proxy_headers=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        deadline=time.monotonic()+12
        while not (server.started and app.state.receiver.snapshot()['connected']) and time.monotonic()<deadline:
            time.sleep(.05)
        assert server.started and app.state.receiver.snapshot()['connected']
        publisher_thread=threading.Thread(target=publish,daemon=True);publisher_thread.start()
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            page=browser.new_page(ignore_https_errors=True,viewport={'width':1400,'height':1100})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url)
            page.get_by_label('Identifiant',exact=True).fill('test-doctor')
            page.get_by_label('Mot de passe',exact=True).fill(password)
            page.get_by_role('button',name='Se connecter',exact=True).click()
            expect(page.locator('#patient-title')).to_have_text('Patient panne')
            page.locator('#technical-details summary').click()
            expect(page.locator('#device-list')).to_contain_text('Données reçues',timeout=12000)
            expect(page.locator('#patient-state')).to_have_text('Normal')
            phase[0]='silence'
            expect(page.locator('#patient-state')).to_have_text('Capteur déconnecté',timeout=15000)
            expect(page.locator('#technical-alerts')).to_contain_text('Aucune nouvelle mesure valide')
            page.locator('#technical-details').scroll_into_view_if_needed()
            page.screenshot(path='/tmp/smartcare-disconnection.png',full_page=True)
            page.get_by_role('button',name=f'Sélectionner Patient témoin {second}').click()
            expect(page.locator('#patient-state')).to_have_text('Normal')
            expect(page.locator('#device-list')).to_contain_text('Données reçues')
            page.get_by_role('button',name=f'Sélectionner Patient panne {first}').click()
            phase[0]='normal'
            expect(page.locator('#patient-state')).to_have_text('Normal',timeout=15000)
            expect(page.locator('#technical-alerts')).to_be_empty()
            phase[0]='missing'
            expect(page.locator('#technical-alerts')).to_contain_text('Paramètres attendus absents',timeout=15000)
            expect(page.locator('#patient-state')).to_have_text('À surveiller')
            expect(page.locator('#device-list')).to_contain_text('Glycémie')
            page.get_by_text('Autres mesures',exact=True).click()
            expect(page.locator('.vital').filter(has_text='Glycémie')).to_have_class(re.compile(r'.*stale.*'))
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path='/tmp/smartcare-missing-data-mobile.png',full_page=True)
            phase[0]='normal'
            expect(page.locator('#patient-state')).to_have_text('Normal',timeout=15000)
            expect(page.locator('#technical-alerts')).to_be_empty()
            with factory() as store:
                episodes=store.connection.execute("SELECT type,status FROM technical_events WHERE type IN ('DISCONNECTED','MISSING_DATA') AND patient_id=%s",(first,)).fetchall()
                assert {e['type'] for e in episodes}=={'DISCONNECTED','MISSING_DATA'}
                assert all(e['status']=='RESOLVED' for e in episodes)
            assert not errors,errors
            browser.close()
        print('OK : chaîne TLS complète, capteur silencieux, patient témoin, récupération, paramètre manquant et mobile.')
        print('Captures : /tmp/smartcare-disconnection.png et /tmp/smartcare-missing-data-mobile.png')
    finally:
        stop.set()
        if publisher_thread:publisher_thread.join(timeout=8)
        if server:
            server.should_exit=True;thread.join(timeout=12)
        with PostgresStore(schema=schema) as store:
            store.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':
    main()
