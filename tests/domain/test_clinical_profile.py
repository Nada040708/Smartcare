from src.domain.clinical_profile import (
    ClinicalProfile,
    DiabetesProfile,
    HypertensionProfile,
    AnxietyProfile,
)


def test_profile_definitions():
    expected = [
        (DiabetesProfile(), "diabetes", ["glucose", "activity", "heart_rate"]),
        (HypertensionProfile(), "hypertension", ["systolic_bp", "diastolic_bp", "heart_rate"]),
        (AnxietyProfile(), "anxiety", ["heart_rate", "hrv", "respiratory_rate", "activity"]),
    ]
    for profile, profile_id, priorities in expected:
        assert isinstance(profile, ClinicalProfile)
        assert profile.profile_id == profile_id
        assert profile.priority_parameters == priorities
        assert profile.get_rules()
        assert all(rule.rule_id.startswith(profile_id + "_") for rule in profile.get_rules())


def test_profile_configuration_is_not_shared_between_instances():
    first = DiabetesProfile()
    second = DiabetesProfile()
    original_rules = second.get_rules()
    first.priority_parameters.append("spo2")
    first.rules.clear()

    assert "spo2" not in second.priority_parameters
    assert second.get_rules() == original_rules
    returned_rules = second.get_rules()
    returned_rules.clear()
    assert second.get_rules() == original_rules


def test_custom_profile_copies_and_deduplicates_priorities():
    priorities = ["heart_rate", "spo2", "heart_rate"]
    profile = ClinicalProfile("custom", "Custom", "Example", priorities)
    priorities.clear()

    assert profile.priority_parameters == ["heart_rate", "spo2"]
