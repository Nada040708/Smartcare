from .generation_strategy import GenerationStrategy, require_finite


class RecoveryStrategy(GenerationStrategy):
    """
    Gradually brings an abnormal value back toward a normal value.
    """

    def __init__(self, target_value: float, step: float = 2.0):
        require_finite(target_value, "target_value")
        require_finite(step, "step")
        if step <= 0:
            raise ValueError("step must be positive")
        self.target_value = target_value
        self.step = step

    def generate(self, current_value: float) -> float:
        require_finite(current_value, "current_value")
        if current_value < self.target_value:
            current_value += self.step

            if current_value > self.target_value:
                current_value = self.target_value

        elif current_value > self.target_value:
            current_value -= self.step

            if current_value < self.target_value:
                current_value = self.target_value

        return round(current_value, 1)
