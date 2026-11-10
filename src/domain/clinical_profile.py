from collections.abc import Iterable
from .monitoring_rule import MonitoringRule
from .rule_catalog import load_rules


class ClinicalProfile:
    """Describe monitoring priorities; a profile does not make a diagnosis."""

    def __init__(
        self,
        profile_id: str,
        name: str,
        description: str,
        priority_parameters: Iterable[str],
        rules: Iterable[MonitoringRule] = (),
    ):
        self.profile_id = profile_id
        self.name = name
        self.description = description
        self.priority_parameters = list(dict.fromkeys(priority_parameters))
        self.rules: list[MonitoringRule] = list(rules)

    def get_rules(self) -> list[MonitoringRule]:
        """Return a copy of the configured immutable rule objects."""
        return list(self.rules)


class DiabetesProfile(ClinicalProfile):
    def __init__(self, rules=None):
        super().__init__(
            profile_id="diabetes",
            name="Diabète",
            description="Suivi de la glycémie, de l'activité et de la fréquence cardiaque.",
            priority_parameters=["glucose", "activity", "heart_rate"],
            rules=load_rules("diabetes") if rules is None else rules,
        )


class HypertensionProfile(ClinicalProfile):
    def __init__(self, rules=None):
        super().__init__(
            profile_id="hypertension",
            name="Hypertension",
            description="Suivi de la pression artérielle et de la fréquence cardiaque.",
            priority_parameters=["systolic_bp", "diastolic_bp", "heart_rate"],
            rules=load_rules("hypertension") if rules is None else rules,
        )


class AnxietyProfile(ClinicalProfile):
    def __init__(self, rules=None):
        super().__init__(
            profile_id="anxiety",
            name="Trouble anxieux / suivi stress",
            description="Suivi physiologique contextualisé par l'activité, sans diagnostic.",
            priority_parameters=["heart_rate", "hrv", "respiratory_rate", "activity"],
            rules=load_rules("anxiety") if rules is None else rules,
        )
