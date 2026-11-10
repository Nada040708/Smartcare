import pytest


def pytest_addoption(parser):
    parser.addoption("--mqtt-integration", action="store_true", help="Run tests requiring the local MQTT/Node-RED stack")
    parser.addoption("--postgres-integration", action="store_true", help="Run tests requiring the local PostgreSQL service")
    parser.addoption('--tls-integration', action='store_true', help='Run tests requiring compose.secure.yaml and .secrets')


def pytest_configure(config):
    config.addinivalue_line("markers", "mqtt_integration: requires Mosquitto and the Smartcare Node-RED flow")
    config.addinivalue_line("markers", "postgres_integration: requires the Smartcare PostgreSQL service")
    config.addinivalue_line('markers', 'tls_integration: requires the secure MQTT/Node-RED profile')


def pytest_collection_modifyitems(config, items):
    for item in items:
        for marker, option in [('mqtt_integration', '--mqtt-integration'), ('postgres_integration', '--postgres-integration'), ('tls_integration', '--tls-integration')]:
            if marker in item.keywords and not config.getoption(option):
                item.add_marker(pytest.mark.skip(reason=f'Start docker compose, then use {option}'))
