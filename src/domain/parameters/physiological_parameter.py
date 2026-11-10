from abc import ABC, abstractmethod
from datetime import datetime, timezone
import random
from uuid import uuid4

from src.domain.measurement import Measurement


class PhysiologicalParameter(ABC):
    """
    Abstract base class for a physiological parameter.
    """

    def __init__(
        self,
        name: str,
        unit: str,
        normal_min: float | None = None,
        normal_max: float | None = None,
    ):
        self.name = name
        self.unit = unit
        self.normal_min = normal_min
        self.normal_max = normal_max
        self.value: float | dict[str, float] | None = None
        self.timestamp: datetime | None = None
        self.reading_id: str | None = None

    @abstractmethod
    def generate(self) -> float | dict[str, float]:
        """
        Generate a value for the physiological parameter.
        """
        pass

    def get_value(self) -> float | dict[str, float] | None:
        return self.value

    def _record_value(self, value: float | dict[str, float]) -> None:
        self.value = value
        self.timestamp = datetime.now(timezone.utc)
        self.reading_id = str(uuid4())

    def record_value(self, value: float | dict[str, float]) -> None:
        """Record a strategy output, restoring the last reading if invalid."""
        previous = (self.value, self.timestamp, self.reading_id)
        self._record_value(dict(value) if isinstance(value, dict) else value)
        try:
            values = self.get_values()
            expected = set(self.get_metadata().get("components", {self.name: {}}))
            if set(values) != expected:
                raise ValueError("Reading components do not match this parameter")
            self.to_measurements("validation", "validation")
        except (ValueError, TypeError):
            self.value, self.timestamp, self.reading_id = previous
            raise

    def _generate_scalar(self) -> float:
        """Sample a demonstration interval, not a clinical decision threshold."""
        value = round(random.uniform(self.normal_min, self.normal_max), 1)
        self._record_value(value)
        return value

    def get_values(self) -> dict[str, float]:
        if self.value is None:
            return {}
        if isinstance(self.value, dict):
            return dict(self.value)
        return {self.name: self.value}

    def to_measurements(
        self, patient_id: str, device_id: str, quality: str = "valid",
    ) -> list[Measurement]:
        """Snapshot the last generated reading; never generate implicitly."""
        values = self.get_values()
        if not values or self.timestamp is None or self.reading_id is None:
            raise ValueError("Generate a reading before creating measurements")
        measurements = [
            Measurement(
                measurement_id=str(uuid4()), patient_id=patient_id,
                device_id=device_id, parameter=parameter, value=value,
                unit=self.unit, timestamp=self.timestamp, quality=quality,
                reading_id=self.reading_id, device_type="simulator",
            )
            for parameter, value in values.items()
        ]
        if not all(measurement.validate() for measurement in measurements):
            raise ValueError("Invalid reading or patient/device identifiers")
        return measurements

    def is_normal(self) -> bool:
        """
        Check whether the current value is within the normal range.
        """
        if self.value is None or self.normal_min is None or self.normal_max is None:
            return False

        return self.normal_min <= self.value <= self.normal_max

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "normal_min": self.normal_min,
            "normal_max": self.normal_max,
        }
