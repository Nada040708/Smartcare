import random

from .generation_strategy import GenerationStrategy


class NormalStrategy(GenerationStrategy):
    """
    Generates small random variations within the normal range.
    """

    def __init__(
        self,
        normal_min: float,
        normal_max: float,
    ):
        self.normal_min = normal_min
        self.normal_max = normal_max

    def generate(self, current_value: float) -> float:
        variation = random.uniform(-1.0, 1.0)
        new_value = current_value + variation

        new_value = max(
            self.normal_min,
            min(new_value, self.normal_max),
        )

        return round(new_value, 1)