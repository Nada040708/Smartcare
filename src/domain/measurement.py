import json
import math
from datetime import datetime, timezone

from .ieee11073_metadata import IEEE11073Metadata
from .parameter_definitions import PARAMETER_DEFINITIONS


def is_finite_number(value: object) -> bool:
    """JSON measurements must not contain booleans, NaN or infinities."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


class Measurement:
    """A scalar reading, with a temporary adapter for prototype `values` batches.

    New callers supply device_id, parameter, value and unit as keywords.
    Legacy callers may still supply values as the third positional argument.
    Clinical thresholds are evaluated later, not by this structural validator.
    """

    def __init__(
        self,
        measurement_id: str,
        patient_id: str,
        values: dict | None = None,
        quality: str = "good",
        timestamp: datetime | None = None,
        *,
        device_id: str | None = None,
        parameter: str | None = None,
        value: float | None = None,
        unit: str | None = None,
        reading_id: str | None = None,
        device_type: str = "unspecified",
    ):
        if values is not None and any(item is not None for item in (parameter, value, unit)):
            raise ValueError("Use either legacy values or parameter/value/unit, not both")
        self.measurement_id = measurement_id
        self.patient_id = patient_id
        self.device_id = device_id
        self.timestamp = datetime.now(timezone.utc) if timestamp is None else timestamp
        self.parameter = parameter
        self.value = value
        self.unit = unit
        self.quality = quality
        self.reading_id = measurement_id if reading_id is None else reading_id
        self.device_type = device_type
        self._legacy = values is not None
        self._legacy_values = dict(values) if isinstance(values, dict) else values

    @property
    def values(self) -> dict:
        """Compatibility view consumed by the existing dashboard and detector."""
        if self._legacy:
            return self._legacy_values
        return {self.parameter: self.value}

    @property
    def ieee11073_metadata(self) -> IEEE11073Metadata | None:
        # Derived from the reading so timestamp and quality cannot diverge.
        if self._legacy:
            return None
        return IEEE11073Metadata.for_parameter(
            self.parameter, self.timestamp, self.quality, self.device_type,
        )

    def validate(self) -> bool:
        if not all(_nonempty_string(item) for item in (self.measurement_id, self.patient_id)):
            return False
        if not isinstance(self.timestamp, datetime):
            return False
        if not isinstance(self.quality, str) or self.quality not in {
            "good", "valid", "questionable", "invalid",
        }:
            return False
        if self._legacy:
            return (
                isinstance(self.values, dict)
                and bool(self.values)
                and all(_nonempty_string(k) and is_finite_number(v) for k, v in self.values.items())
            )
        if not all(_nonempty_string(item) for item in (
            self.device_id, self.parameter, self.unit, self.reading_id, self.device_type,
        )):
            return False
        definition = PARAMETER_DEFINITIONS.get(self.parameter)
        if definition is None or self.unit != definition.unit:
            return False
        if self.timestamp.utcoffset() is None or not is_finite_number(self.value):
            return False
        # Only enforce the definition of this local index, not clinical limits.
        if self.parameter == "activity" and not 0 <= self.value <= 1:
            return False
        return True

    def to_dict(self) -> dict:
        if not self.validate():
            raise ValueError("Cannot serialize an invalid measurement")
        data = {
            "measurement_id": self.measurement_id,
            "patient_id": self.patient_id,
            "timestamp": self.timestamp.isoformat(),
            "quality": self.quality,
        }
        if self._legacy:
            data["values"] = dict(self.values)
        else:
            data.update(
                device_id=self.device_id,
                reading_id=self.reading_id,
                parameter=self.parameter,
                value=self.value,
                unit=self.unit,
                ieee11073_metadata=self.ieee11073_metadata.to_dict(),
            )
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)
