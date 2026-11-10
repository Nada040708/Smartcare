from .generation_strategy import GenerationStrategy


class MissingDataStrategy(GenerationStrategy):
    """Omit a reading: absence is not a numeric zero or a stale measurement."""

    def generate(self, current_value: float) -> None:
        return None
