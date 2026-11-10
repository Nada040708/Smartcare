#!/bin/sh
set -eu
umask 077
# Runtime copies belong to Mosquitto, independently of macOS bind-mount ownership.
mkdir -p /run/smartcare
cp /mosquitto/security/passwords /run/smartcare/passwords
cp /mosquitto/config/acl /run/smartcare/acl
cp /mosquitto/tls/broker.key /run/smartcare/broker.key
cp /mosquitto/tls/broker.crt /run/smartcare/broker.crt
chown -R mosquitto:mosquitto /run/smartcare
chmod 700 /run/smartcare
chmod 600 /run/smartcare/*
exec /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf
