import random

from .physiological_parameter import PhysiologicalParameter


class SpO2(PhysiologicalParameter):
    """
    Blood oxygen saturation parameter measured in percentage.
    """

    def __init__(self):
        super().__init__(
            name="spo2",
            unit="%",
            normal_min=95.0,
            normal_max=100.0,
        )

    def generate(self) -> float:
        self.value = round(random.uniform(95.0, 100.0), 1)
        return self.value