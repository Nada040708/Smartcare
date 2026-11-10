from .physiological_parameter import PhysiologicalParameter


class Glucose(PhysiologicalParameter):
    """Synthetic concentration; the demo interval is not a clinical threshold."""

    def __init__(self):
        super().__init__("glucose", "mg/dL", 80.0, 130.0)

    def generate(self) -> float:
        return self._generate_scalar()
