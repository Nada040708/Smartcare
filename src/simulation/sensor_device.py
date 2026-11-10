from abc import ABC, abstractmethod

from src.domain.measurement import Measurement


class SensorDevice(ABC):
    """Identity and read interface of a device assigned to one patient."""

    def __init__(self, device_id: str, patient_id: str):
        for name, value in (("device_id", device_id), ("patient_id", patient_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        self.device_id = device_id
        self.patient_id = patient_id

    @property
    @abstractmethod
    def status(self) -> str:
        pass

    def get_status(self) -> str:
        return self.status

    @abstractmethod
    def read(self) -> list[Measurement]:
        pass
