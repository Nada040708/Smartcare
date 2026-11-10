"""One MQTT loop owns the stateful processor and its database connection."""
from copy import deepcopy
import json
import logging
import queue
import re
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import paho.mqtt.client as mqtt

from src.processing.persistent_monitoring import PersistentMonitoring
from src.processing.connection_monitor import ConnectionMonitor, load_connection_policy
from src.repositories.postgres_store import PostgresStore

logger = logging.getLogger(__name__)


class MonitoringReceiver:
    def __init__(self, patients, *, schema='smartcare', broker='localhost', port=1883, security=None, connection_policy=None):
        self.patients, self.schema, self.broker, self.port = patients, schema, broker, port
        self.security = security
        self.connection_policy = connection_policy or load_connection_policy()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._commands = queue.Queue()
        self._status = dict(running=False, connected=False, error=None, processed=0, rejected=0,
                            last_received_at=None, evaluated_at=None, states={})

    def snapshot(self):
        with self._lock:
            return deepcopy(self._status)

    def _update(self, **values):
        with self._lock:
            self._status.update(values)

    def start(self):
        self._thread = threading.Thread(target=self._run, name='smartcare-receiver', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=8)

    def resolve_alert(self, alert_id, actor_id, timeout=5):
        if not self.snapshot()['running']:
            raise RuntimeError('Monitoring receiver is not running')
        completed = threading.Event()
        command = {'kind':'resolve_alert', 'alert_id':alert_id, 'actor_id':actor_id,
                   'completed':completed, 'result':None, 'error':None}
        self._commands.put(command)
        if not completed.wait(timeout):
            raise RuntimeError('Monitoring command timed out')
        if command['error']:
            raise command['error']
        return command['result']

    def handle_message(self, session, topic, payload, retained=False):
        match = re.fullmatch(r'health/([A-Za-z0-9_-]+)/received', topic)
        if retained or not match or len(payload) > 65536:
            raise ValueError('Invalid receipt topic, retained message or oversized payload')
        patient_id = match.group(1)
        if patient_id not in self.patients:
            raise ValueError('Unknown patient')
        # The payload is still validated in its original form, including patient/topic identity.
        return session.process_payload(payload, self.patients[patient_id], topic=f'health/{patient_id}/vitals')

    def _run(self):
        retry = 1
        while not self._stop.is_set():
            try:
                self._run_session()
                break
            except Exception as error:
                logger.error('Monitoring session interrupted (%s)', type(error).__name__)
                self._update(running=False, connected=False, error='MONITORING_UNAVAILABLE')
                self._stop.wait(retry)
                retry = min(retry * 2, 10)
        self._update(running=False, connected=False)

    def _run_session(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'smartcare-web-{uuid4()}', manual_ack=True)
        client.connect_timeout = 3
        try:
            if self.security:
                self.security.configure(client)
            with PostgresStore(schema=self.schema) as store:
                session = PersistentMonitoring(store,
                    connection_monitor=ConnectionMonitor(self.connection_policy, self.patients),
                    auto_resolve_alerts=False)

                def on_connect(client, userdata, flags, reason_code, properties):
                    if reason_code.is_failure:
                        self._update(connected=False, error='MQTT_UNAVAILABLE')
                    else:
                        client.subscribe('health/+/received', qos=1)

                def on_subscribe(client, userdata, mid, reason_codes, properties):
                    good = bool(reason_codes) and all(not code.is_failure for code in reason_codes)
                    self._update(connected=good, error=None if good else 'MQTT_UNAVAILABLE')

                def on_disconnect(client, userdata, flags, reason_code, properties):
                    self._update(connected=False, error='MQTT_UNAVAILABLE')

                def on_message(client, userdata, message):
                    try:
                        self.handle_message(session, message.topic, message.payload, message.retain)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        with self._lock:
                            self._status['rejected'] += 1
                    else:
                        with self._lock:
                            self._status['processed'] += 1
                            self._status['last_received_at'] = datetime.now(timezone.utc).isoformat()
                        self._publish_states(session)
                    # Invalid messages are discarded; database errors escape and stop the receiver.
                    client.ack(message.mid, message.qos)

                client.on_connect, client.on_subscribe = on_connect, on_subscribe
                client.on_disconnect, client.on_message = on_disconnect, on_message
                self._update(running=True, error=None)
                next_evaluation = 0
                next_connect, backoff = 0, 1
                while not self._stop.is_set():
                    self._drain_commands(session)
                    # Timers keep running even when MQTT is unavailable.
                    if time.monotonic() >= next_evaluation:
                        for patient in self.patients.values():
                            session.process([], patient)
                        self._publish_states(session)
                        next_evaluation = time.monotonic() + 1
                    if not client.is_connected() and time.monotonic() >= next_connect:
                        try:
                            client.connect(self.broker, self.port, keepalive=30)
                        except OSError:
                            self._update(connected=False, error='MQTT_UNAVAILABLE')
                        next_connect = time.monotonic() + backoff
                        backoff = min(backoff * 2, 10)
                    result = client.loop(timeout=0.2)
                    if result != mqtt.MQTT_ERR_SUCCESS:
                        self._update(connected=False, error='MQTT_UNAVAILABLE')
                        self._stop.wait(.2)
                    elif self.snapshot()['connected']:
                        backoff = 1
        finally:
            client.disconnect()

    def _drain_commands(self, session):
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                if command['kind'] == 'resolve_alert':
                    command['result'] = session.resolve_alert(command['alert_id'], command['actor_id'])
            except Exception as error:
                command['error'] = error
            finally:
                command['completed'].set()

    def _publish_states(self, session):
        self._update(states={pid: state.value for pid, state in session.states.current_states.items()},
                     evaluated_at=datetime.now(timezone.utc).isoformat())
