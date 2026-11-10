// Explicit local HTTPS viewer. Anonymous users cannot read flows or deploy changes.
const fs = require('fs');
module.exports = {
    ...require('./settings.secure.js'),
    httpAdminRoot: '/',
    disableEditor: false,
    https: {cert: fs.readFileSync('/run/secrets/editor.crt'), key: fs.readFileSync('/run/secrets/editor.key')},
    adminAuth: {type:'credentials', sessionExpiryTime:3600,
        users:[JSON.parse(fs.readFileSync('/run/secrets/editor.json','utf8'))]},
    editorTheme: {projects:{enabled:false}, palette:{editable:false}},
};
