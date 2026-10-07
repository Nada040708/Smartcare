from abc import ABC, abstractmethod


class GenerationStrategy(ABC):
    """
    Strategy interface for generating physiological values.
    """

    @abstractmethod
    def generate(self, current_value: float) -> float:
        """
        Generate the next value from the current value.
        """
        pass