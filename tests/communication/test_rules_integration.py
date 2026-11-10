import pytest
from examples.step6_rules import verify_mqtt_rules


@pytest.mark.mqtt_integration
def test_node_red_receipts_feed_profile_rules_and_alerts():
    anomalies,alerts=verify_mqtt_rules()
    assert len(anomalies)==len(alerts)==5
    assert {a.patient_id for a in alerts}=={'P001','P002'}
    assert all(a.rule_id and a.measurement_ids for a in alerts)
    assert len({a.alert_id for a in alerts})==5
