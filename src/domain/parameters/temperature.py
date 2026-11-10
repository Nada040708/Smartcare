from .physiological_parameter import PhysiologicalParameter


class Temperature(PhysiologicalParameter):
    """
    Body temperature parameter measured in degrees Celsius.
    """

    def __init__(self):
        super().__init__(
            name="temperature",
            unit="°C",
            normal_min=36.0,
            normal_max=37.5,
        )

    def generate(self) -> float:
        return self._generate_scalar()
