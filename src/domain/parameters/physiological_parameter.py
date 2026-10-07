from abc import ABC, abstractmethod


class PhysiologicalParameter(ABC):
    """
    Abstract base class for a physiological parameter.
    """

    def __init__(
        self,
        name: str,
        unit: str,
        normal_min: float,
        normal_max: float,
    ):
        self.name = name
        self.unit = unit
        self.normal_min = normal_min
        self.normal_max = normal_max
        self.value: float | None = None

    @abstractmethod
    def generate(self) -> float:
        """
        Generate a value for the physiological parameter.
        """
        pass

    def get_value(self) -> float | None:
        return self.value

    def is_normal(self) -> bool:
        """
        Check whether the current value is within the normal range.
        """
        if self.value is None:
            return False

        return self.normal_min <= self.value <= self.normal_max

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "normal_min": self.normal_min,
            "normal_max": self.normal_max,
        }