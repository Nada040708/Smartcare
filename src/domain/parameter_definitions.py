"""Shared parameter identifiers and units; these are not clinical thresholds."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterDefinition:
    unit: str
    description: str


PARAMETER_DEFINITIONS = {
    "heart_rate": ParameterDefinition("bpm", "Heart rate"),
    "spo2": ParameterDefinition("%", "Oxygen saturation by pulse oximetry"),
    "temperature": ParameterDefinition("°C", "Body temperature"),
    "systolic_bp": ParameterDefinition("mmHg", "Non-invasive systolic blood pressure"),
    "diastolic_bp": ParameterDefinition("mmHg", "Non-invasive diastolic blood pressure"),
    "glucose": ParameterDefinition("mg/dL", "Simulated glucose concentration"),
    "respiratory_rate": ParameterDefinition("breaths/min", "Respiratory rate"),
    "hrv": ParameterDefinition("ms", "Simulated RMSSD, not computed from RR intervals"),
    "activity": ParameterDefinition("1", "Local simulated activity index from 0 to 1"),
}
