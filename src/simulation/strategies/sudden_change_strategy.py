from .generation_strategy import GenerationStrategy, require_finite


class SuddenChangeStrategy(GenerationStrategy):
    """Apply one jump after N unchanged readings, then keep the new value."""

    def __init__(self, change: float = 15.0, trigger_after: int = 0):
        require_finite(change, "change")
        if isinstance(trigger_after, bool) or not isinstance(trigger_after, int) or trigger_after < 0:
            raise ValueError("trigger_after must be a non-negative integer")
        self.change = change
        self.trigger_after = trigger_after
        self.reset()

    def reset(self) -> None:
        self._calls = 0
        self._triggered = False

    def generate(self, current_value: float) -> float:
        require_finite(current_value, "current_value")
        self._calls += 1
        if not self._triggered and self._calls > self.trigger_after:
            self._triggered = True
            return round(current_value + self.change, 1)
        return current_value
