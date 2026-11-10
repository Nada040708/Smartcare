"""Browser check against a local dashboard, with explicit test credentials."""
import argparse
from getpass import getpass
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect


def main(argv=None, *, password=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='https://127.0.0.1:8000')
    parser.add_argument('--username',default='admin')
    parser.add_argument('--local-test-ca',action='store_true')
    parser.add_argument('--screenshots',default='/tmp')
    args=parser.parse_args(argv)
    if urlparse(args.url).hostname not in {'127.0.0.1','localhost','::1'}:parser.error('Local only')
    output=Path(args.screenshots);output.mkdir(parents=True,exist_ok=True)
    password=password or getpass('Mot de passe du compte de test : ')
    errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000},ignore_https_errors=args.local_test_ca)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.url)
        page.get_by_label('Identifiant',exact=True).fill(args.username)
        page.get_by_label('Mot de passe',exact=True).fill(password)
        with page.expect_response(lambda r:'/api/auth/login' in r.url) as login:
            page.get_by_role('button',name='Se connecter',exact=True).click()
        assert login.value.status==200
        expect(page.get_by_role('heading',name='Surveillance',exact=True)).to_be_visible(timeout=15000)
        expect(page.locator('.patient-button')).to_have_count(3)
        expect(page.locator('#patient-title')).to_have_text('Patient 01')
        expect(page.locator('#chart svg')).to_be_visible()
        expect(page.locator('#vitals .vital')).to_have_count(4)
        expect(page.locator('#other-vitals')).not_to_be_visible()
        page.get_by_text('Autres mesures',exact=True).focus()
        page.keyboard.press('Enter')
        expect(page.locator('#other-vitals')).to_be_visible()
        page.keyboard.press('Enter')
        page.get_by_role('button',name='Mettre en pause').click()
        expect(page.get_by_role('button',name='Reprendre le suivi')).to_be_visible()
        page.screenshot(path=str(output/'smartcare-dashboard-desktop.png'),full_page=True)
        page.get_by_role('button',name='Sélectionner Patient 02 P002').click()
        expect(page.locator('#profiles')).to_contain_text('Trouble anxieux')
        page.get_by_label('Paramètre affiché').select_option('hrv')
        expect(page.locator('#chart-caption')).to_contain_text('Variabilité cardiaque')
        page.get_by_role('button',name='24 h',exact=True).click()
        expect(page.get_by_role('button',name='24 h',exact=True)).to_have_attribute('aria-pressed','true')
        page.locator('.topbar nav a[href="/alerts"]').click()
        expect(page.get_by_role('heading',name='Alertes physiologiques')).to_be_visible()
        expect(page.locator('#alert-rows')).to_contain_text('Critique')
        expect(page.get_by_label('Afficher')).to_have_value('ALL')
        page.get_by_label('Afficher').select_option('ACTIVE')
        expect(page.locator('#alert-rows')).to_contain_text('Active')
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(output/'smartcare-alerts-mobile.png'),full_page=True)
        page.get_by_role('link',name='Surveillance',exact=True).click()
        expect(page.locator('#chart svg')).to_be_visible()
        page.locator('.topbar nav a[href="/audit"]').click()
        expect(page.get_by_role('heading',name='Audit de surveillance')).to_be_visible()
        expect(page.get_by_role('heading',name='État des capteurs')).to_be_visible()
        page.get_by_role('link',name='Surveillance',exact=True).click()
        page.route('**/api/overview',lambda r:r.fulfill(status=503,json={'detail':'Test outage'}))
        page.get_by_role('button',name='Actualiser',exact=True).click()
        expect(page.locator('#error')).to_contain_text('Actualisation impossible')
        expect(page.locator('#receiver-status')).to_have_text('Service indisponible')
        expect(page.locator('#patient-state')).not_to_have_text('Normal')
        page.unroute('**/api/overview')
        page.get_by_role('button',name='Actualiser',exact=True).click()
        expect(page.locator('#error')).not_to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(output/'smartcare-dashboard-mobile.png'),full_page=True)
        page.get_by_role('button',name='Se déconnecter').click()
        expect(page).to_have_url(args.url+'/login')
        assert not errors,errors
        browser.close()
    print('OK : deux vues, patients, courbe, filtres, clavier, pause, panne API, mobile et déconnexion.')


if __name__=='__main__':main()
