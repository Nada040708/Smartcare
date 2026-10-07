from src.domain.patient import Patient
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