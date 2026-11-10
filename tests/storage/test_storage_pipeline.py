import pytest

from examples.step8_storage import seed, resume, inspect


@pytest.mark.postgres_integration
@pytest.mark.mqtt_integration
def test_node_red_receipts_are_persisted_and_resume_without_duplicate_episode(postgres_schema):
    seed(postgres_schema, mqtt=True)
    resume(postgres_schema)
    result = inspect(postgres_schema)
    assert result['measurements'] == 6
    assert result['alerts'] == 1 and result['active_alerts'] == 0
    assert result['events'] >= 4
