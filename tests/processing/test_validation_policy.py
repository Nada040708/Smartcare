import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.processing import DataValidator
from src.domain import Measurement
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.domain.ieee11073_metadata import VERIFIED_MDC_MAPPINGS

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/validation_cases.json'
CONTRACT = json.loads(FIXTURES.read_text())


@pytest.mark.parametrize('case', CONTRACT['cases'], ids=lambda c: c['name'])
def test_received_validation_contract(case):
    validator = DataValidator(now=lambda: datetime.fromisoformat(CONTRACT['now']))
    result = validator.validate_payload(case['payload'], topic=case['topic'], retained=case['retained'])
    assert result.accepted is (not case['codes'])
    assert sorted({error['code'] for error in result.errors}) == sorted(case['codes'])


def test_shared_policy_matches_domain_units_and_verified_mdc_codes():
    policy = DataValidator().policy
    assert set(policy['parameters']) == set(PARAMETER_DEFINITIONS)
    for name, definition in PARAMETER_DEFINITIONS.items():
        parameter = policy['parameters'][name]
        assert parameter['unit'] == definition.unit
        assert parameter['minimum'] <= parameter['maximum']
        expected = VERIFIED_MDC_MAPPINGS.get(name, (None, None, None, None))
        assert tuple(parameter[key] for key in ('metric_code','metric_refid','unit_code','unit_refid')) == expected


@pytest.mark.parametrize('bad', [None, [], {}, 'text', 42, True])
def test_unexpected_input_types_do_not_crash_legacy_methods(bad):
    validator = DataValidator()
    assert not validator.validate(bad)
    assert not validator.validate_format(bad)
    assert not validator.validate_range(bad)
    assert not validator.validate_timestamp(bad)
    assert not validator.validate_quality(bad)


def test_local_legacy_quality_unknown_parameters_and_naive_time_are_rejected():
    validator = DataValidator()
    m = Measurement('M1', 'P001', values={'heart_rate':84}, quality='questionable')
    assert not validator.validate(m)
    m.quality = 'good'
    m.timestamp = datetime.now()
    assert not validator.validate(m)
    m.timestamp = datetime.now(timezone.utc)
    assert validator.validate(m)
    assert not validator.validate(Measurement('M2', 'P001', values={'unknown':84}))


def test_json_non_finite_constants_and_invalid_utf8_are_rejected():
    for payload in ['{"value": NaN}', '{"value": Infinity}', b'\xff']:
        assert DataValidator().validate_payload(payload).errors[0]['code'] == 'invalid_json'
