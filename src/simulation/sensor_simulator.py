from src.domain.measurement import Measurement
from src.domain.patient import Patient
from src.simulation.strategies import GenerationStrategy


class SensorSimulator:
    """
    Simulates a physiological sensor for one or more patients.
    """

    def __init__(self, interval: int = 1):
        self.interval = interval
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def generate_measurement(
        self,
        patient: Patient,
        strategies: dict[str, GenerationStrategy],
    ) -> Measurement:

        values = {}

        for parameter in patient.parameters:
            strategy = strategies.get(parameter.name)

            if strategy is None:
                values[parameter.name] = parameter.generate()
            else:
                current_value = parameter.get_value()

                if current_value is None:
                    current_value = parameter.generate()

                parameter.value = strategy.generate(current_value)
                values[parameter.name] = parameter.get_value()

        return Measurement(
            measurement_id=f"M-{patient.patient_id}",
            patient_id=patient.patient_id,
            values=values,
        )