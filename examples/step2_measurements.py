"""Run with: python -m examples.step2_measurements (no MQTT broker required)."""

from src.domain import Patient, DiabetesProfile, HypertensionProfile, AnxietyProfile
from src.domain.parameters import (
    HeartRate, SpO2, Temperature, BloodPressure, Glucose, RespiratoryRate, HRV, Activity,
)


def main():
    patients = [
        Patient("P001", "Patient 1", profiles=[DiabetesProfile(), HypertensionProfile()]),
        Patient("P002", "Patient 2", profiles=[AnxietyProfile()]),
    ]
    parameters_by_patient = [
        [HeartRate(), SpO2(), Temperature(), BloodPressure(), Glucose(), Activity()],
        [HeartRate(), HRV(), RespiratoryRate(), Activity()],
    ]
    for patient, parameters in zip(patients, parameters_by_patient):
        for parameter in parameters:
            patient.add_parameter(parameter)
            parameter.generate()
            device_id = f"SIM_{patient.patient_id}_{parameter.name.upper()}"
            for measurement in parameter.to_measurements(patient.patient_id, device_id):
                print(measurement.to_json())


if __name__ == "__main__":
    main()
