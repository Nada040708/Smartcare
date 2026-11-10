from copy import deepcopy

from src.domain.measurement import Measurement, is_finite_number
from src.domain.patient import Patient
from src.domain.parameters import PhysiologicalParameter
from src.simulation.sensor_device import SensorDevice
from src.simulation.strategies import GenerationStrategy


class SensorSimulator(SensorDevice):
    """A virtual multiparameter device for one patient, advanced one cycle at a time.

    Parameters and strategies are copied so separate simulators cannot share
    readings or scenario counters. The caller controls scheduling via interval.
    """

    def __init__(
        self,
        patient: Patient,
        interval: float = 1,
        device_id: str | None = None,
        strategies: dict[str, GenerationStrategy] | None = None,
    ):
        if not isinstance(patient, Patient):
            raise TypeError("patient must be a Patient")
        if not is_finite_number(interval) or interval <= 0:
            raise ValueError("interval must be a positive finite number")
        super().__init__(
            device_id=f"SIM_{patient.patient_id}" if device_id is None else device_id,
            patient_id=patient.patient_id,
        )
        self.patient = patient
        self.interval = interval
        self.running = False
        self._failed = False
        self._parameters = deepcopy(patient.parameters)
        self._components: set[str] = set()
        for parameter in self._parameters:
            if not isinstance(parameter, PhysiologicalParameter):
                raise TypeError("patient parameters must be PhysiologicalParameter instances")
            names = set(parameter.get_metadata().get("components", {parameter.name: {}}))
            if self._components.intersection(names):
                raise ValueError("Each physiological parameter must be configured only once")
            self._components.update(names)
        self._strategies: dict[str, GenerationStrategy] = {}
        for name, strategy in (strategies or {}).items():
            self.set_strategy(name, strategy)

    @property
    def status(self) -> str:
        if not self.running:
            return "STOPPED"
        if self._failed:
            return "FAILED"
        if not self.patient.monitoring_enabled:
            return "DISABLED"
        return "RUNNING"

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def simulate_failure(self) -> None:
        self._failed = True

    def restore(self) -> None:
        """Clear a device failure without starting a stopped device."""
        self._failed = False

    def set_strategy(self, parameter: str, strategy: GenerationStrategy | None) -> None:
        """Assign/reset a component's scenario; None restores default generation."""
        if parameter not in self._components:
            raise ValueError(f"Unknown or unconfigured parameter: {parameter}")
        if strategy is None:
            self._strategies.pop(parameter, None)
            return
        if not isinstance(strategy, GenerationStrategy):
            raise TypeError("strategy must implement GenerationStrategy")
        owned_strategy = deepcopy(strategy)
        owned_strategy.reset()
        self._strategies[parameter] = owned_strategy

    def read(self) -> list[Measurement]:
        if self.status != "RUNNING":
            return []
        if self.patient.patient_id != self.patient_id:
            raise ValueError("A simulator cannot be reassigned by changing patient_id")

        # Commit only a fully valid cycle. No corrupted reading or consumed jump
        # remains in the simulator if a strategy produces an invalid result.
        parameters = deepcopy(self._parameters)
        strategies = deepcopy(self._strategies)
        measurements = []
        for index, parameter in enumerate(parameters):
            names = set(parameter.get_metadata().get("components", {parameter.name: {}}))
            configured = names.intersection(strategies)
            if not configured:
                parameter.generate()
            else:
                if parameter.value is None:
                    parameter.generate()
                values = parameter.get_values()
                next_values = {
                    name: strategies[name].generate(value) if name in configured else value
                    for name, value in values.items()
                }
                if any(value is None for value in next_values.values()):
                    # A missing BP component suppresses the whole cuff reading.
                    parameters[index] = self._parameters[index]
                    for name in configured:
                        strategies[name] = self._strategies[name]
                    continue
                parameter.record_value(
                    next_values if "components" in parameter.get_metadata()
                    else next_values[parameter.name]
                )
            measurements.extend(parameter.to_measurements(self.patient_id, self.device_id))

        self._parameters = parameters
        self._strategies = strategies
        return measurements

    def generate_measurements(self) -> list[Measurement]:
        return self.read()
