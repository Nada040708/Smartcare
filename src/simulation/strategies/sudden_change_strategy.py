from .generation_strategy import GenerationStrategy


class SuddenChangeStrategy(GenerationStrategy):
    """
    Applies a sudden change to the current value.
    """

    def __init__(self, change: float = 15.0):
        self.change = change

    def generate(self, current_value: float) -> float:
        return round(current_value + self.change, 1)