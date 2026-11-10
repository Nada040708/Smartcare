import random

from .generation_strategy import GenerationStrategy, require_finite


class NormalStrategy(GenerationStrategy):
    """
    Generates small random variations within the normal range.
    """

    def __init__(
        self,
        normal_min: float,
        normal_max: float,
    ):
        require_finite(normal_min, "normal_min")
        require_finite(normal_max, "normal_max")
        if normal_min > normal_max:
            raise ValueError("normal_min must not exceed normal_max")
        self.normal_min = normal_min
        self.normal_max = normal_max

    def generate(self, current_value: float) -> float:
        require_finite(current_value, "current_value")
        variation = random.uniform(-1.0, 1.0)
        new_value = current_value + variation

        new_value = max(
            self.normal_min,
            min(new_value, self.normal_max),
        )

        return max(self.normal_min, min(round(new_value, 1), self.normal_max))
