"""Exercise step 10 in an isolated database and HTTPS server; remove test accounts afterwards."""
from pathlib import Path
import secrets
import ssl
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from playwright.sync_api import sync_playwright, expect
from psycopg import sql
import uvicorn

from src.repositories.postgres_store import PostgresStore
from src.security.authentication import AuthenticationService
from src.web.app import create_app


def main():
    schema='smartcare_browser_'+uuid4().hex
    factory=lambda:PostgresStore(schema=schema,initialize=False)
    password=secrets.token_urlsafe(24)
    url='https://127.0.0.1:8443'
    server=None
    try:
        with PostgresStore(schema=schema):
            pass
        service=AuthenticationService(factory)
        service.create_user('browser-admin',password,'ADMIN',bootstrap=True)
        app=create_app(ingest=False,store_factory=factory)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8443,log_level='warning',
            proxy_headers=False,ssl_certfile=str(ROOT/'.secrets/tls/web.crt'),ssl_keyfile=str(ROOT/'.secrets/tls/web.key')))
        thread=threading.Thread(target=server.run,daemon=True)
        thread.start()
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:
            time.sleep(.05)
        assert server.started, 'Test HTTPS server did not start (port 8443 must be free)'
        # Verify the certificate chain and hostname independently of the disposable browser trust exception.
        with httpx.Client(verify=ssl.create_default_context(cafile=str(ROOT/'.secrets/tls/ca.crt'))) as http:
            assert http.get(url+'/login').status_code==200
            assert http.get(url+'/api/overview').status_code==401
        errors=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000})
            # Local test CA only; production clients never disable certificate verification.
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url)
            expect(page).to_have_url(url+'/login')
            page.screenshot(path='/tmp/smartcare-login-desktop.png',full_page=True)
            page.get_by_role('link',name='Demander un compte',exact=True).click()
            expect(page.get_by_role('heading',name='Demander un compte',exact=True)).to_be_visible()
            page.get_by_label('Identifiant professionnel').fill('browser-pending')
            page.get_by_label('Fonction').select_option('DOCTOR')
            page.get_by_label('Mot de passe',exact=True).fill(password)
            page.get_by_role('button',name='Envoyer la demande',exact=True).click()
            expect(page.locator('#signup-message')).to_contain_text('administrateur')
            page.get_by_role('link',name='Retour à la connexion',exact=True).click()
            page.get_by_label('Identifiant',exact=True).fill('browser-admin')
            page.get_by_label('Mot de passe',exact=True).fill('Incorrect-password')
            page.get_by_role('button',name='Se connecter',exact=True).click()
            expect(page.locator('#login-error')).to_contain_text('incorrect')
            page.get_by_label('Mot de passe',exact=True).fill(password)
            page.get_by_role('button',name='Se connecter',exact=True).click()
            expect(page.get_by_role('heading',name='Surveillance',exact=True)).to_be_visible()
            expect(page.locator('#account-label')).to_contain_text('Administrateur')
            page.get_by_role('link',name='Administration',exact=True).click()
            expect(page.get_by_role('heading',name='Administration',exact=True)).to_be_visible()
            pending=page.locator('#users tr').filter(has_text='browser-pending')
            expect(pending).to_contain_text('En attente')
            pending.get_by_role('button',name='Valider le compte').click()
            expect(pending).to_contain_text('Actif')
            patient=page.locator('#create-patient')
            patient.get_by_label('Identifiant patient').fill('P900')
            patient.get_by_label('Nom affiché').fill('Patient navigateur')
            patient.get_by_label('Diabète').check()
            patient.get_by_role('button',name='Ajouter le patient').click()
            expect(page.locator('#admin-message')).to_have_text('Modification enregistrée.')
            page.locator('#consent-section summary').click()
            page.locator('#audit-section summary').click()
            consent=page.locator('#consents tr').filter(has_text='P001')
            consent.get_by_role('button',name='Retirer le consentement').click()
            expect(consent).to_contain_text('Non accordé')
            expect(page.locator('#audit')).to_contain_text('Consentement retiré')
            page.goto(url)
            expect(page.locator('#notice')).to_contain_text('consentement')
            expect(page.locator('#chart svg')).to_have_count(0)
            assert context.request.get(url+'/api/patients/P001/history').status==403
            page.goto(url+'/admin')
            page.locator('#consent-section summary').click()
            page.locator('#audit-section summary').click()
            consent.get_by_role('button',name='Enregistrer l’accord').click()
            expect(consent).to_contain_text('Accordé')
            form=page.locator('#create-user')
            form.get_by_label('Identifiant',exact=True).fill('browser-doctor')
            form.get_by_label('Mot de passe initial',exact=True).fill(password)
            form.get_by_role('button',name='Créer le compte').click()
            expect(page.locator('#users')).to_contain_text('browser-doctor')
            expect(page.locator('#audit')).to_contain_text('Compte créé')
            row=page.locator('#users tr').filter(has_text='browser-doctor')
            row.get_by_role('button',name='Désactiver',exact=True).click()
            expect(row).to_contain_text('Désactivé')
            row.get_by_role('button',name='Réactiver',exact=True).click()
            expect(row).to_contain_text('Actif')
            row.get_by_label('Rôle de browser-doctor').select_option('NURSE')
            row.get_by_role('button',name='Enregistrer le rôle').click()
            expect(page.locator('#admin-message')).to_have_text('Modification enregistrée.')
            expect(row.get_by_label('Rôle de browser-doctor')).to_have_value('NURSE')
            page.get_by_text('Réinitialiser un mot de passe',exact=True).click()
            reset=page.locator('#reset-password')
            reset.get_by_label('Compte',exact=True).select_option(label='browser-doctor')
            clinician_password=secrets.token_urlsafe(24)
            reset.get_by_label('Nouveau mot de passe').fill(clinician_password)
            with page.expect_response(lambda response:'/api/admin/users/' in response.url and response.request.method=='PATCH') as changed:
                reset.get_by_role('button',name='Enregistrer',exact=True).click()
            assert changed.value.status==200
            page.locator('#consent-section summary').click()
            page.locator('#audit-section summary').click()
            page.get_by_text('Réinitialiser un mot de passe',exact=True).click()
            page.screenshot(path='/tmp/smartcare-admin-desktop.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path='/tmp/smartcare-admin-mobile.png',full_page=True)
            page.get_by_role('button',name='Se déconnecter',exact=True).click()
            expect(page).to_have_url(url+'/login')
            page.screenshot(path='/tmp/smartcare-login-mobile.png',full_page=True)
            page.get_by_label('Identifiant',exact=True).fill('browser-doctor')
            page.get_by_label('Mot de passe',exact=True).fill(clinician_password)
            page.get_by_role('button',name='Se connecter',exact=True).click()
            expect(page.locator('#account-label')).to_contain_text('Infirmier')
            expect(page.locator('#admin-link')).not_to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert context.request.get(url+'/api/admin/users').status==403
            assert context.request.get(url+'/api/admin/audit').status==403
            assert cookie_not_visible(page)
            # Revocation while the page is open must clear the data and request a new login.
            with factory() as store:
                store.connection.execute('DELETE FROM auth_sessions')
            page.get_by_role('button',name='Actualiser',exact=True).click()
            expect(page).to_have_url(url+'/login')
            assert not errors, errors
            browser.close()
        print('OK : HTTPS vérifié, connexion, refus, comptes, rôles, audit, déconnexion, révocation et mobile.')
        print('Captures : /tmp/smartcare-login-{desktop,mobile}.png et /tmp/smartcare-admin-{desktop,mobile}.png')
    finally:
        if server:
            server.should_exit=True
            thread.join(timeout=10)
        with PostgresStore(schema=schema) as store:
            store.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def cookie_not_visible(page):
    return 'smartcare_session' not in page.evaluate('document.cookie')


if __name__=='__main__':
    main()
