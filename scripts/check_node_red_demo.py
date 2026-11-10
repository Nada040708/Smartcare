"""Check the local authenticated Node-RED viewer with disposable credentials only."""
from pathlib import Path
import json
import os
import secrets
import ssl
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from src.demo import compose,prepare_editor


def main():
    password=secrets.token_urlsafe(24)
    previous=os.environ.get('SMARTCARE_DEMO_ADMIN_PASSWORD')
    os.environ['SMARTCARE_DEMO_ADMIN_PASSWORD']=password
    secure=compose('smartcare-validation')
    with tempfile.TemporaryDirectory(prefix='smartcare-editor-') as folder:
        directory=Path(folder)
        try:
            prepare_editor(directory)
            before=(directory/'editor.json').read_bytes();prepare_editor(directory)
            assert (directory/'editor.json').read_bytes()==before
            overlay=directory/'editor-override.json'
            overlay.write_text(json.dumps({'services':{'node-red':{'volumes':[f'{directory}/editor.json:/run/secrets/editor.json:ro']}}}))
            command=compose('smartcare-validation',editor=True)+['-f',str(overlay)]
            config=json.loads(subprocess.check_output(command+['config','--format','json'],text=True))
            ports=config['services']['node-red']['ports']
            assert all(p['host_ip']=='127.0.0.1' for p in ports)
            subprocess.run(command+['up','-d','--wait'],check=True)
            with httpx.Client(base_url='https://127.0.0.1:1880',verify=ssl.create_default_context(cafile=str(ROOT/'.secrets/tls/ca.crt'))) as client:
                assert client.get('/').status_code==200
                assert client.get('/flows').status_code==401
                assert client.post('/auth/token',data={'client_id':'node-red-editor','grant_type':'password','scope':'*','username':'admin','password':'incorrect'}).status_code!=200
                login=client.post('/auth/token',data={'client_id':'node-red-editor','grant_type':'password','scope':'','username':'admin','password':password})
                login.raise_for_status();client.headers['Authorization']='Bearer '+login.json()['access_token']
                flows=client.get('/flows');flows.raise_for_status()
                nodes=flows.json()
                assert any(n['type']=='mqtt in' for n in nodes)
                assert any(n['type']=='function' for n in nodes)
                # Node-RED's permission middleware returns 401 even for a valid read-only token.
                assert client.post('/flows',json=nodes).status_code==401
            print('OK : Node-RED HTTPS localhost, compte authentifié en lecture seule, flow visible, écriture/anonyme refusés, initialisation conservatrice.')
        finally:
            subprocess.run(secure+['up','-d','--wait'],check=True)
            if previous is None:os.environ.pop('SMARTCARE_DEMO_ADMIN_PASSWORD',None)
            else:os.environ['SMARTCARE_DEMO_ADMIN_PASSWORD']=previous


if __name__=='__main__':main()
