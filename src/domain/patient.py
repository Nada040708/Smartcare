from collections.abc import Iterable

from src.domain.clinical_profile import ClinicalProfile
from src.domain.parameters import PhysiologicalParameter
from src.domain.consent import Consent


class Patient:
    """
    Represents a patient monitored by the system.
    """

    def __init__(
        self,
        patient_id: str,
        name: str,
        monitoring_enabled: bool = True,
        profiles: Iterable[ClinicalProfile] | None = None,
        consent: Consent | None = None,
    ):
        self.patient_id = patient_id
        self.name = name
        self.monitoring_enabled = monitoring_enabled
        if consent is not None and (not isinstance(consent, Consent) or consent.patient_id != patient_id):
            raise ValueError('Consent must belong to this patient')
        self.consent = consent
        self.profiles: list[ClinicalProfile] = []
        self.parameters: list[PhysiologicalParameter] = []
        if profiles is not None:
            for profile in profiles:
                self.add_profile(profile)

    def add_profile(self, profile: ClinicalProfile) -> None:
        """Attach a profile once, using its stable identifier."""
        if not isinstance(profile, ClinicalProfile):
            raise TypeError("profile must be a ClinicalProfile instance")
        if not any(p.profile_id == profile.profile_id for p in self.profiles):
            self.profiles.append(profile)

    def remove_profile(self, profile: ClinicalProfile) -> None:
        """Remove a profile by identity key; an absent profile is a no-op."""
        if not isinstance(profile, ClinicalProfile):
            raise TypeError("profile must be a ClinicalProfile instance")
        self.profiles[:] = [
            p for p in self.profiles if p.profile_id != profile.profile_id
        ]

    def get_priority_parameters(self) -> list[str]:
        """Combine profile priorities without duplicates, preserving their order."""
        return list(dict.fromkeys(
            parameter
            for profile in self.profiles
            for parameter in profile.priority_parameters
        ))

    def add_parameter(self, parameter: PhysiologicalParameter) -> None:
        self.parameters.append(parameter)

    def remove_parameter(self, parameter: PhysiologicalParameter) -> None:
        if parameter in self.parameters:
            self.parameters.remove(parameter)
