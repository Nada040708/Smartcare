from .generation_strategy import GenerationStrategy


class ProgressiveStrategy(GenerationStrategy):
    """
    Progressively increases the current value.
    """

    def __init__(self, step: float = 2.0):
        self.step = step

    def generate(self, current_value: float) -> float:
        return round(current_value + self.step, 1)