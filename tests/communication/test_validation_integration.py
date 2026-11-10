import pytest
from examples.step5_validation import verify_validation


@pytest.mark.mqtt_integration
def test_node_red_accepts_and_rejects_with_expected_reasons():
    cases = verify_validation()
    assert len(cases) == 8
    assert sum(case['code'] is None for case in cases) == 1
