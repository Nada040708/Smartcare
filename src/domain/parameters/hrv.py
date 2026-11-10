from .physiological_parameter import PhysiologicalParameter


class HRV(PhysiologicalParameter):
    """Synthetic RMSSD in ms, without calculating an RR-interval series."""

    def __init__(self):
        super().__init__("hrv", "ms", 30.0, 70.0)

    def generate(self) -> float:
        return self._generate_scalar()
