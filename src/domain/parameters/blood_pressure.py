import random

from src.domain.measurement import is_finite_number
from .physiological_parameter import PhysiologicalParameter


class BloodPressure(PhysiologicalParameter):
    """One cuff reading with two components sharing a timestamp and reading ID."""

    def __init__(self):
        super().__init__("blood_pressure", "mmHg")
        self.systolic_range = (110.0, 130.0)
        self.diastolic_range = (70.0, 85.0)

    @property
    def systolic(self) -> float | None:
        return self.value["systolic_bp"] if self.value is not None else None

    @property
    def diastolic(self) -> float | None:
        return self.value["diastolic_bp"] if self.value is not None else None

    def generate(self) -> dict[str, float]:
        self._record_value({
            "systolic_bp": round(random.uniform(*self.systolic_range), 1),
            "diastolic_bp": round(random.uniform(*self.diastolic_range), 1),
        })
        return self.get_values()

    def get_values(self) -> dict[str, float]:
        if self.value is None:
            return {}
        if not isinstance(self.value, dict) or set(self.value) != {"systolic_bp", "diastolic_bp"}:
            raise ValueError("Blood pressure requires systolic and diastolic components")
        if not all(is_finite_number(value) for value in self.value.values()):
            raise ValueError("Blood pressure components must be finite numbers")
        if not 0 < self.diastolic < self.systolic:
            raise ValueError("Blood pressure requires 0 < diastolic < systolic")
        return dict(self.value)

    def is_normal(self) -> bool:
        """Whether both components fall in the demo intervals, not a diagnosis."""
        try:
            values = self.get_values()
        except ValueError:
            return False
        return bool(values) and (
            self.systolic_range[0] <= self.systolic <= self.systolic_range[1]
            and self.diastolic_range[0] <= self.diastolic <= self.diastolic_range[1]
        )

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "components": {
                "systolic_bp": {"demo_min": self.systolic_range[0], "demo_max": self.systolic_range[1]},
                "diastolic_bp": {"demo_min": self.diastolic_range[0], "demo_max": self.diastolic_range[1]},
            },
        }
