import json
from datetime import datetime


class Measurement:
    """
    Represents a physiological measurement for a patient.
    """

    def __init__(
        self,
        measurement_id: str,
        patient_id: str,
        values: dict,
        quality: str = "good",
        timestamp: datetime | None = None,
    ):
        self.measurement_id = measurement_id
        self.patient_id = patient_id
        self.timestamp = timestamp or datetime.now()
        self.values = values
        self.quality = quality

    def to_json(self) -> str:
        data = {
            "measurement_id": self.measurement_id,
            "patient_id": self.patient_id,
            "timestamp": self.timestamp.isoformat(),
            "values": self.values,
            "quality": self.quality,
        }

        return json.dumps(data)

    def validate(self) -> bool:
        if not self.measurement_id:
            return False

        if not self.patient_id:
            return False

        if not isinstance(self.values, dict):
            return False

        if not self.values:
            return False

        if not self.quality:
            return False

        return True