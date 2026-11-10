from .physiological_parameter import PhysiologicalParameter


class RespiratoryRate(PhysiologicalParameter):
    def __init__(self):
        super().__init__("respiratory_rate", "breaths/min", 12.0, 20.0)

    def generate(self) -> float:
        return self._generate_scalar()
