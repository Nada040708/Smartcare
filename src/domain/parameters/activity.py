from .physiological_parameter import PhysiologicalParameter


class Activity(PhysiologicalParameter):
    """Local simulated index: 0 = rest, 1 = high activity; not a medical scale."""

    def __init__(self):
        super().__init__("activity", "1", 0.0, 1.0)

    def generate(self) -> float:
        return self._generate_scalar()
