import random

from .physiological_parameter import PhysiologicalParameter


class HeartRate(PhysiologicalParameter):
    """
    Heart rate parameter measured in beats per minute (bpm).
    """

    def __init__(self):
        super().__init__(
            name="heart_rate",
            unit="bpm",
            normal_min=60.0,
            normal_max=100.0,
        )

    def generate(self) -> float:
        self.value = round(random.uniform(60.0, 100.0), 1)
        return self.value