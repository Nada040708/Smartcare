from src.domain.parameters import PhysiologicalParameter


class Patient:
    """
    Represents a patient monitored by the system.
    """

    def __init__(self, patient_id: str, name: str):
        self.patient_id = patient_id
        self.name = name
        self.parameters: list[PhysiologicalParameter] = []

    def add_parameter(self, parameter: PhysiologicalParameter) -> None:
        self.parameters.append(parameter)

    def remove_parameter(self, parameter: PhysiologicalParameter) -> None:
        if parameter in self.parameters:
            self.parameters.remove(parameter)