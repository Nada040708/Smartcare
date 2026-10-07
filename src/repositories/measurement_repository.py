from src.domain.measurement import Measurement


class MeasurementRepository:
    """
    Stores and retrieves physiological measurements.
    """

    def __init__(self):
        self.measurements: list[Measurement] = []

    def save(self, measurement: Measurement) -> None:
        self.measurements.append(measurement)

    def getByPatient(self, patient_id: str) -> list[Measurement]:
        return [
            measurement
            for measurement in self.measurements
            if measurement.patient_id == patient_id
        ]

    def getHistory(self) -> list[Measurement]:
        return self.measurements.copy()