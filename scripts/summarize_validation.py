"""Combine JUnit reports without counting the same test twice; fail on missing coverage."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def main():
    all_cases=set();passed=set();failures=[];profiles=[]
    for name in ('secure','legacy'):
        path=ROOT/'reports'/f'pytest-{name}.xml'
        root=ET.parse(path).getroot()
        counts={'profile':name,'passed':0,'skipped':0,'failed':0}
        for case in root.iter('testcase'):
            key=case.attrib['classname']+'::'+case.attrib['name']
            all_cases.add(key)
            if case.find('failure') is not None or case.find('error') is not None:
                failures.append(key);counts['failed']+=1
            elif case.find('skipped') is not None:counts['skipped']+=1
            else:passed.add(key);counts['passed']+=1
        profiles.append(counts)
    missing=sorted(all_cases-passed)
    result={'status':'PASSED' if not failures and not missing else 'FAILED',
            'unique_collected':len(all_cases),'unique_passed':len(passed),
            'profiles':profiles,'failures':failures,'never_executed':missing}
    (ROOT/'reports/step12_tests.json').write_text(json.dumps(result,indent=2)+'\n')
    rows='\n'.join(f"| {p['profile']} | {p['passed']} | {p['skipped']} | {p['failed']} |" for p in profiles)
    (ROOT/'reports/step12_tests.md').write_text('# Bilan des tests automatisés\n\n'
        f"**{result['status']} — {len(passed)} / {len(all_cases)} cas distincts réussis.**\n\n"
        '| Profil | Réussis | Exclus de ce profil | Échecs |\n| --- | --- | --- | --- |\n'+rows+'\n\n'
        'Les exclusions de chaque profil sont exécutées sous l’autre profil. '
        'Le bilan refuse de réussir si un cas n’a jamais été exécuté ou si un échec apparaît.\n\n'
        'Preuves : [profil sécurisé](pytest-secure.xml), [profil historique](pytest-legacy.xml), '
        '[bilan JSON](step12_tests.json).\n\n'
        'Un avertissement non bloquant signale la dépréciation de httpx dans Starlette TestClient. '
        'Ces nombres concernent pytest ; les contrôles Chromium et les KPI sont documentés séparément '
        'dans [l’étape 12](../docs/step12_validation.md).\n')
    print(result)
    if failures or missing:raise SystemExit(1)


if __name__=='__main__':main()
