#!/bin/sh
set -eu
# Seed once: preserve subsequent edits made through the Node-RED editor.
if [ ! -f /data/smartcare-flows.json ]; then
    cp /opt/smartcare/flows.json /data/smartcare-flows.json
fi
exec node /usr/src/node-red/node_modules/node-red/red.js --userDir /data --settings /opt/smartcare/settings.js
