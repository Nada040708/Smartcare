from .generation_strategy import GenerationStrategy


class RecoveryStrategy(GenerationStrategy):
    """
    Gradually brings an abnormal value back toward a normal value.
    """

    def __init__(self, target_value: float, step: float = 2.0):
        self.target_value = target_value
        self.step = step

    def generate(self, current_value: float) -> float:
        if current_value < self.target_value:
            current_value += self.step

            if current_value > self.target_value:
                current_value = self.target_value

        elif current_value > self.target_value:
            current_value -= self.step

            if current_value < self.target_value:
                current_value = self.target_value

        return round(current_value, 1)