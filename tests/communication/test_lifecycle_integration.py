import pytest

from examples.step7_alerts import run_demo


@pytest.mark.mqtt_integration
def test_node_red_receipts_drive_alert_episodes_and_patient_states():
    snapshots, history = run_demo(mqtt=True)
    assert snapshots[5]['active'] == 4  # Replayed normal measurements do not resolve.
    assert snapshots[6]['active'] == 0
    assert len(history) == len({a.alert_id for a in history}) == 8
    assert all(a.status == 'RESOLVED' and a.resolution_reason == 'RECOVERY_CONFIRMED' for a in history[:4])
    assert all(a.status == 'ACTIVE' for a in history[4:])
