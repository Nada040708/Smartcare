const fs = require('fs');
const {spawn} = require('child_process');
process.umask(0o077);
const flows = JSON.parse(fs.readFileSync('/opt/smartcare/flows.json','utf8'));
const credentials = JSON.parse(fs.readFileSync('/run/secrets/node-red.json','utf8'));
for (const node of flows) {
    if (node.type === 'debug') { node.active = false; node.console = false; node.tosidebar = false; }
    if (node.id === 'smartcare-broker') { node.usetls = true; node.tls = 'smartcare-tls'; }
}
flows.push({id:'smartcare-tls', type:'tls-config', name:'CA Smartcare', cert:'', key:'',
    ca:'/run/secrets/ca.crt', verifyservercert:true, servername:'mosquitto'});
fs.writeFileSync('/secure-data/secure-flows.json',JSON.stringify(flows));
fs.writeFileSync('/secure-data/secure-flows_cred.json',JSON.stringify({
    'smartcare-broker': {user:credentials.username, password:credentials.password}
}));
const child = spawn(process.execPath, ['/usr/src/node-red/node_modules/node-red/red.js',
    '--userDir','/secure-data','--settings',process.env.SMARTCARE_NODE_RED_SETTINGS || '/opt/smartcare/settings.secure.js'], {stdio:'inherit'});
for (const signal of ['SIGTERM','SIGINT']) process.on(signal,()=>child.kill(signal));
child.on('exit',code=>process.exit(code ?? 1));
