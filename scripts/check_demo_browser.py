"""Exercise the documented CLI end to end on the smartcare-validation Docker project only."""
from pathlib import Path
import os
import secrets
import signal
import ssl
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from playwright.sync_api import sync_playwright,expect
from psycopg import sql
from src.repositories.postgres_store import PostgresStore
from src.demo import prepare_secrets


def stop(process):
    if process and process.poll() is None:
        process.send_signal(signal.SIGINT if os.name!='nt' else signal.SIGTERM)
        try:process.wait(timeout=12)
        except subprocess.TimeoutExpired:process.kill();process.wait()


def main():
    schema='smartcare_browser_'+uuid4().hex
    password=secrets.token_urlsafe(24)
    env=dict(os.environ,SMARTCARE_DEMO_ADMIN_PASSWORD=password)
    url='https://127.0.0.1:8445'
    server=simulator=None;errors=[]
    output=ROOT/'reports/simplification';output.mkdir(exist_ok=True)
    # All generated credentials here are disposable; production keys are never regenerated.
    with tempfile.TemporaryDirectory(prefix='smartcare-setup-') as folder:
        directory=Path(folder)/'secrets';prepare_secrets(directory)
        before={p.relative_to(directory):p.read_bytes() for p in directory.rglob('*') if p.is_file()}
        prepare_secrets(directory)
        assert before=={p.relative_to(directory):p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    with tempfile.TemporaryFile(mode='w+') as logs:
        def start():
            return subprocess.Popen([sys.executable,'smartcare.py','start-demo','--project','smartcare-validation','--db-schema',schema,'--port','8445'],cwd=ROOT,env=env,stdout=logs,stderr=logs)
        def ready():
            with httpx.Client(verify=ssl.create_default_context(cafile=str(ROOT/'.secrets/tls/ca.crt'))) as client:
                deadline=time.monotonic()+35
                while time.monotonic()<deadline:
                    if server.poll() is not None:raise AssertionError('Demo command failed; no credentials printed')
                    try:
                        if client.get(url+'/login').status_code==200:return
                    except httpx.TransportError:pass
                    time.sleep(.1)
                raise AssertionError('Demo startup timeout')
        def scenario(name):
            return subprocess.Popen([sys.executable,'smartcare.py','simulate',name,'--duration','90'],cwd=ROOT,env=env,stdout=logs,stderr=logs)
        try:
            server=start();ready()
            with sync_playwright() as pw:
                browser=pw.chromium.launch()
                page=browser.new_page(ignore_https_errors=True,viewport={'width':1440,'height':1000})
                page.clock.install()
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(url)
                page.get_by_label('Identifiant',exact=True).fill('admin')
                page.get_by_label('Mot de passe',exact=True).fill(password)
                page.get_by_role('button',name='Se connecter',exact=True).click()
                expect(page.locator('#vitals')).to_contain_text('Aucune mesure')
                expect(page.locator('#patient-state')).not_to_have_text('Normal')
                simulator=scenario('normal')
                expect(page.locator('#patient-state')).to_have_text('Normal',timeout=30000)
                expect(page.locator('#chart svg')).to_be_visible()
                page.screenshot(path=str(output/'surveillance-desktop.png'),full_page=True)
                stop(simulator);simulator=scenario('anomaly')
                expect(page.locator('#patient-state')).to_have_text('Alerte',timeout=15000)
                expect(page.locator('#alert-rows')).to_contain_text('Glycémie')
                expect(page.locator('#vitals')).to_contain_text('240')
                page.get_by_role('button',name='Sélectionner Patient 02 P002').click()
                expect(page.locator('#patient-state')).to_have_text('Normal')
                page.get_by_role('button',name='Sélectionner Patient 01 P001').click()
                stop(simulator);simulator=scenario('disconnection')
                expect(page.locator('#patient-state')).to_have_text('Normal',timeout=12000)
                expect(page.locator('#patient-state')).to_have_text('Capteur déconnecté',timeout=40000)
                expect(page.locator('#technical-alerts')).to_contain_text('Incident technique')
                page.get_by_role('link',name='Alertes',exact=True).click()
                expect(page.locator('#technical-alerts')).to_contain_text('P001')
                page.screenshot(path=str(output/'alerts-desktop.png'),full_page=True)
                page.get_by_role('link',name='Surveillance',exact=True).click()
                expect(page.locator('#patient-state')).to_have_text('Normal',timeout=30000)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(output/'surveillance-mobile.png'),full_page=True)
                # Real authentication and clock-based stale display, with no fabricated readings.
                stop(simulator);simulator=None
                page.get_by_role('button',name='Mettre en pause').click()
                page.clock.fast_forward(121000)
                expect(page.locator('#vitals .stale')).to_have_count(4)
                expect(page.locator('#patient-state')).not_to_have_text('Normal')
                with PostgresStore(schema=schema) as store:
                    assert store.connection.execute("SELECT count(*) AS n FROM measurements WHERE payload->>'encrypted'='fernet-v1'").fetchone()['n']>0
                    assert store.connection.execute("SELECT count(*) AS n FROM technical_events WHERE type='DISCONNECTED' AND status='RESOLVED' AND patient_id='P001'").fetchone()['n']>0
                    old=store.connection.execute('SELECT user_id,password_hash FROM users').fetchone()
                assert not errors,errors
                browser.close()
            stop(server)
            env['SMARTCARE_DEMO_ADMIN_PASSWORD']='Another-disposable-password'
            server=start();ready()
            with PostgresStore(schema=schema) as store:
                assert store.connection.execute('SELECT user_id,password_hash FROM users').fetchone()==old
            with httpx.Client(verify=ssl.create_default_context(cafile=str(ROOT/'.secrets/tls/ca.crt'))) as client:
                assert client.post(url+'/api/auth/login',headers={'Origin':url},json={'username':'admin','password':password}).status_code==200
            print('OK : setup neuf et conservateur, CLI premier/deuxième démarrage, normal/anomalie/coupure/reprise, témoin, données anciennes, chiffrement, desktop/mobile.')
        finally:
            stop(simulator);stop(server)
            with PostgresStore(schema=schema) as store:
                store.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':main()
