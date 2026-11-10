const base = require('./settings.js');
module.exports = {
    ...base,
    flowFile: 'secure-flows.json',
    // This profile is an immutable orchestrator: no editor, Admin API or public port.
    httpAdminRoot: false,
    disableEditor: true,
    credentialSecret: false, // Credentials exist only on a private tmpfs, never in a persistent volume.
    logging: {console: {level: 'warn', metrics: false, audit: false}},
};
