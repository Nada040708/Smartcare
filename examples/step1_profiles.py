"""Run with: python -m examples.step1_profiles."""

from src.domain import Patient, DiabetesProfile, HypertensionProfile, AnxietyProfile


def main():
    first = Patient("P001", "Patient 1", profiles=[DiabetesProfile(), HypertensionProfile()])
    second = Patient("P002", "Patient 2", profiles=[AnxietyProfile()])
    first.add_profile(DiabetesProfile())  # same ID: no duplicate
    for patient in [first, second]:
        print(patient.patient_id, [profile.name for profile in patient.profiles])
        print("Priorités :", patient.get_priority_parameters())
        print("Surveillance activée :", patient.monitoring_enabled)
    first.remove_profile(DiabetesProfile())
    print("P001 après retrait :", [profile.name for profile in first.profiles])


if __name__ == "__main__":
    main()
