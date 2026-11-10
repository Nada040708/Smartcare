"""Input validation using the same technical policy as the Node-RED flow."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from src.domain.measurement import Measurement, is_finite_number

POLICY_PATH = Path(__file__).resolve().parents[2] / "config/validation-policy.json"
ISO_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
REQUIRED_TEXT = ("measurement_id", "reading_id", "patient_id", "device_id", "parameter", "unit", "timestamp", "quality")
CODE_FIELDS = ("metric_code", "metric_refid", "unit_code", "unit_refid", "mapping_status")


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[dict, ...] = ()

    @property
    def accepted(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {"accepted": self.accepted, "errors": list(self.errors)}


def parse_timestamp(value):
    if not isinstance(value, str) or not ISO_TIMESTAMP.fullmatch(value):
        return None
    if int(value[11:13]) > 23 or int(value[14:16]) > 59 or int(value[17:19]) > 59:
        return None
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def reject_json_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


class DataValidator:
    def __init__(self, policy_path=POLICY_PATH, now=None):
        self.policy = json.loads(Path(policy_path).read_text())
        self.now = now or (lambda: datetime.now(timezone.utc))
        for key in ("max_age_seconds", "max_future_seconds"):
            if not is_finite_number(self.policy[key]) or self.policy[key] < 0:
                raise ValueError(f"Invalid policy: {key}")

    def _timestamp_code(self, timestamp):
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            return "invalid_timestamp"
        age = (self.now() - timestamp).total_seconds()
        if age > self.policy["max_age_seconds"]:
            return "stale_timestamp"
        if age < -self.policy["max_future_seconds"]:
            return "future_timestamp"
        return None

    def validate_payload(self, payload, topic=None, retained=False) -> ValidationResult:
        """Inspect raw received fields, without recreating/replacing metadata."""
        if isinstance(payload, (str, bytes)):
            try:
                payload = json.loads(payload, parse_constant=reject_json_constant)
            except (ValueError, UnicodeDecodeError):
                return ValidationResult(({"code": "invalid_json", "field": "payload"},))
        errors = []
        def add(code, field):
            errors.append({"code": code, "field": field})
        if not isinstance(payload, dict) or "values" in payload:
            return ValidationResult(({"code": "invalid_format", "field": "payload"},))
        for key in REQUIRED_TEXT:
            if not isinstance(payload.get(key), str) or not payload[key].strip():
                add("invalid_format", key)
        if errors:
            return ValidationResult(tuple(errors))
        if not re.fullmatch(r"[A-Za-z0-9_-]+", payload["patient_id"]):
            add("invalid_format", "patient_id")
        if topic is not None and topic != f"health/{payload['patient_id']}/vitals":
            add("topic_mismatch", "topic")
        if retained:
            add("retained_message", "retain")
        parameter = self.policy["parameters"].get(payload["parameter"])
        if parameter is None:
            add("unknown_parameter", "parameter")
        elif payload["unit"] != parameter["unit"]:
            add("unit_mismatch", "unit")
        if not is_finite_number(payload.get("value")):
            add("invalid_value", "value")
        elif parameter and not parameter["minimum"] <= payload["value"] <= parameter["maximum"]:
            add("out_of_range", "value")
        code = self._timestamp_code(parse_timestamp(payload["timestamp"]))
        if code:
            add(code, "timestamp")
        if payload["quality"] not in self.policy["accepted_quality"]:
            add("invalid_quality", "quality")
        metadata = payload.get("ieee11073_metadata")
        if not isinstance(metadata, dict):
            add("metadata_mismatch", "ieee11073_metadata")
        else:
            expected = {
                "timestamp": payload["timestamp"], "quality": payload["quality"],
                "nomenclature_system": self.policy["nomenclature_system"],
            }
            if parameter:
                expected.update({key: parameter[key] for key in CODE_FIELDS})
            for key, value in expected.items():
                if key not in metadata or metadata[key] != value:
                    add("metadata_mismatch", f"ieee11073_metadata.{key}")
            if not isinstance(metadata.get("device_type"), str) or not metadata["device_type"].strip():
                add("metadata_mismatch", "ieee11073_metadata.device_type")
        return ValidationResult(tuple(errors))

    def validate_format(self, measurement) -> bool:
        return isinstance(measurement, Measurement) and measurement.validate()

    def validate_range(self, measurement) -> bool:
        if not self.validate_format(measurement):
            return False
        for name, value in measurement.values.items():
            parameter = self.policy["parameters"].get(name)
            if parameter is None or not parameter["minimum"] <= value <= parameter["maximum"]:
                return False
        return True

    def validate_timestamp(self, measurement) -> bool:
        return isinstance(measurement, Measurement) and self._timestamp_code(measurement.timestamp) is None

    def validate_quality(self, measurement) -> bool:
        return isinstance(measurement, Measurement) and measurement.quality in self.policy["accepted_quality"]

    def validate(self, measurement) -> bool:
        if not self.validate_format(measurement):
            return False
        if measurement.parameter is not None:
            return self.validate_payload(measurement.to_dict()).accepted
        # Local compatibility only: legacy batches are never accepted on MQTT.
        return self.validate_range(measurement) and self.validate_timestamp(measurement) and self.validate_quality(measurement)
