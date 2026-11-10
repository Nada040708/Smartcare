from abc import ABC, abstractmethod

from src.domain.measurement import is_finite_number


def require_finite(value: float, name: str) -> None:
    if not is_finite_number(value):
        raise ValueError(f"{name} must be a finite number")


class GenerationStrategy(ABC):
    """Produce a scalar value, or None to simulate no observation."""

    @abstractmethod
    def generate(self, current_value: float) -> float | None:
        pass

    def reset(self) -> None:
        """Reset scenario state when assigning a strategy to a sensor."""
