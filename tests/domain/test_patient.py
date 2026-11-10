import pytest

from src.domain.patient import Patient
from src.domain.clinical_profile import DiabetesProfile, HypertensionProfile
from src.domain.parameters import HeartRate, SpO2


def test_add_parameter():
    patient = Patient("P001", "Patient 1")
    heart_rate = HeartRate()

    patient.add_parameter(heart_rate)

    assert len(patient.parameters) == 1
    assert patient.parameters[0] is heart_rate


def test_remove_parameter():
    patient = Patient("P001", "Patient 1")
    heart_rate = HeartRate()
    spo2 = SpO2()

    patient.add_parameter(heart_rate)
    patient.add_parameter(spo2)

    patient.remove_parameter(heart_rate)

    assert len(patient.parameters) == 1
    assert patient.parameters[0] is spo2


def test_patient_defaults_and_disabled_monitoring():
    patient = Patient("P001", "Patient 1")
    assert patient.monitoring_enabled is True
    assert patient.profiles == []
    assert patient.get_priority_parameters() == []
    disabled = Patient("P002", "Patient 2", monitoring_enabled=False)
    assert disabled.monitoring_enabled is False


def test_multiple_profiles_deduplicate_profiles_and_priorities():
    diabetes = DiabetesProfile()
    patient = Patient("P001", "Patient 1", profiles=[diabetes, HypertensionProfile()])
    patient.add_profile(DiabetesProfile())

    assert len(patient.profiles) == 2
    assert patient.profiles[0] is diabetes
    assert patient.get_priority_parameters() == [
        "glucose", "activity", "heart_rate", "systolic_bp", "diastolic_bp",
    ]


def test_remove_profile_by_identifier_preserves_other_profiles_and_parameters():
    patient = Patient("P001", "Patient 1", profiles=[DiabetesProfile(), HypertensionProfile()])
    spo2 = SpO2()
    patient.add_parameter(spo2)
    patient.remove_profile(DiabetesProfile())
    patient.remove_profile(DiabetesProfile())

    assert [p.profile_id for p in patient.profiles] == ["hypertension"]
    assert patient.get_priority_parameters() == ["systolic_bp", "diastolic_bp", "heart_rate"]
    assert patient.parameters == [spo2]


def test_patient_profile_lists_are_independent():
    profiles = [DiabetesProfile()]
    first = Patient("P001", "Patient 1", profiles=profiles)
    second = Patient("P002", "Patient 2", profiles=profiles)
    profiles.clear()
    first.remove_profile(DiabetesProfile())

    assert first.profiles == []
    assert len(second.profiles) == 1


def test_profile_operations_reject_strings():
    patient = Patient("P001", "Patient 1")
    with pytest.raises(TypeError):
        patient.add_profile("diabetes")
    with pytest.raises(TypeError):
        patient.remove_profile("diabetes")
