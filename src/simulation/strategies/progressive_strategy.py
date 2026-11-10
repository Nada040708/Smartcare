from .generation_strategy import GenerationStrategy, require_finite


class ProgressiveStrategy(GenerationStrategy):
    """
    Progressively changes the current value (a negative step decreases it).
    """

    def __init__(self, step: float = 2.0):
        require_finite(step, "step")
        self.step = step

    def generate(self, current_value: float) -> float:
        require_finite(current_value, "current_value")
        return round(current_value + self.step, 1)
