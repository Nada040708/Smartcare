"""Configurable, immutable rules for the educational monitoring prototype."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import operator as operators

from .measurement import Measurement, is_finite_number
from .parameter_definitions import PARAMETER_DEFINITIONS

OPERATORS = {'>': operators.gt, '>=': operators.ge, '<': operators.lt, '<=': operators.le, '==': operators.eq}


def positive(value, name):
    if not is_finite_number(value) or value <= 0:
        raise ValueError(f'{name} must be positive and finite')


@dataclass(frozen=True)
class Condition:
    parameter: str
    operator: str
    threshold: float

    def __post_init__(self):
        if self.parameter not in PARAMETER_DEFINITIONS or self.operator not in OPERATORS:
            raise ValueError('Unknown parameter or comparison operator')
        if not is_finite_number(self.threshold):
            raise ValueError('Threshold must be finite')

    def matches(self, measurement: Measurement) -> bool:
        return OPERATORS[self.operator](measurement.value, self.threshold)


@dataclass(frozen=True)
class RuleContext:
    history: tuple[Measurement, ...]
    now: datetime

    def samples(self, parameter, window_seconds, device_id=None):
        return sorted((m for m in self.history if m.parameter == parameter
                       and (device_id is None or m.device_id == device_id)
                       and 0 <= (self.now-m.timestamp).total_seconds() <= window_seconds),
                      key=lambda m: (m.timestamp, m.measurement_id))

    def latest(self, parameter, window_seconds):
        samples = self.samples(parameter, window_seconds)
        return samples[-1] if samples else None


@dataclass(frozen=True, kw_only=True)
class MonitoringRule(ABC):
    rule_id: str
    severity: str
    message: str
    window_seconds: float = 120

    def __post_init__(self):
        if not isinstance(self.rule_id,str) or not self.rule_id.strip():
            raise ValueError('rule_id must be non-empty')
        if self.severity not in {'INFO','WARNING','CRITICAL'}:
            raise ValueError('Unknown severity')
        if not isinstance(self.message,str) or not self.message.strip():
            raise ValueError('message must be non-empty')
        positive(self.window_seconds,'window_seconds')

    @property
    @abstractmethod
    def parameters(self) -> tuple[str, ...]:
        pass

    @abstractmethod
    def evaluate(self, context: RuleContext) -> tuple[Measurement, ...] | None:
        """Return evidence if matched, otherwise None (not a patient state)."""

    def get_evidence(self, context: RuleContext) -> tuple[Measurement, ...] | None:
        """Usable observations even when clear; unknown by default for custom rules."""
        return self.evaluate(context)


@dataclass(frozen=True, kw_only=True)
class ThresholdRule(MonitoringRule):
    parameter: str
    operator: str
    threshold: float

    def __post_init__(self):
        super().__post_init__()
        Condition(self.parameter,self.operator,self.threshold)

    @property
    def parameters(self):
        return (self.parameter,)

    def evaluate(self, context):
        samples = self.get_evidence(context)
        if samples and Condition(self.parameter,self.operator,self.threshold).matches(samples[0]):
            return samples
        return None

    def get_evidence(self, context):
        measurement = context.latest(self.parameter,self.window_seconds)
        return (measurement,) if measurement is not None else None


@dataclass(frozen=True, kw_only=True)
class CombinedRule(MonitoringRule):
    conditions: tuple[Condition, ...]
    max_skew_seconds: float = 10
    same_reading: bool = False

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self,'conditions',tuple(self.conditions))
        if len(self.conditions) < 2 or not all(isinstance(c,Condition) for c in self.conditions):
            raise ValueError('Combined rules require at least two conditions')
        if len(set(self.parameters)) != len(self.conditions):
            raise ValueError('Combined parameters must be distinct')
        positive(self.max_skew_seconds,'max_skew_seconds')
        if self.max_skew_seconds > self.window_seconds:
            raise ValueError('max_skew_seconds exceeds window')
        if not isinstance(self.same_reading,bool):
            raise ValueError('same_reading must be boolean')

    @property
    def parameters(self):
        return tuple(c.parameter for c in self.conditions)

    def evaluate(self, context):
        samples = self.get_evidence(context)
        if samples and all(c.matches(m) for c,m in zip(self.conditions,samples)):
            return samples
        return None

    def get_evidence(self, context):
        samples = tuple(context.latest(c.parameter,self.window_seconds) for c in self.conditions)
        if any(m is None for m in samples):
            return None
        if (max(m.timestamp for m in samples)-min(m.timestamp for m in samples)).total_seconds() > self.max_skew_seconds:
            return None
        if self.same_reading and len({(m.device_id,m.reading_id,m.timestamp) for m in samples}) != 1:
            return None
        return samples


@dataclass(frozen=True, kw_only=True)
class TrendRule(MonitoringRule):
    parameter: str
    minimum_delta: float
    min_samples: int = 3
    min_span_seconds: float = 10
    max_gap_seconds: float = 30
    direction: str = 'increasing'

    def __post_init__(self):
        super().__post_init__()
        if self.parameter not in PARAMETER_DEFINITIONS or self.direction not in {'increasing','decreasing'}:
            raise ValueError('Invalid trend parameter or direction')
        positive(self.minimum_delta,'minimum_delta')
        positive(self.min_span_seconds,'min_span_seconds')
        positive(self.max_gap_seconds,'max_gap_seconds')
        if isinstance(self.min_samples,bool) or not isinstance(self.min_samples,int) or self.min_samples < 3:
            raise ValueError('min_samples must be an integer >= 3')
        if self.min_span_seconds > self.window_seconds:
            raise ValueError('Minimum trend span exceeds window')

    @property
    def parameters(self):
        return (self.parameter,)

    def evaluate(self, context):
        samples = self.get_evidence(context)
        if samples is None:
            return None
        sign = 1 if self.direction == 'increasing' else -1
        if any(sign*(current.value-previous.value) <= 0 for previous,current in zip(samples,samples[1:])):
            return None
        if sign*(samples[-1].value-samples[0].value) >= self.minimum_delta:
            return samples
        return None

    def get_evidence(self, context):
        latest = context.latest(self.parameter,self.window_seconds)
        if latest is None:
            return None
        samples = context.samples(self.parameter,self.window_seconds,latest.device_id)
        if len(samples) < self.min_samples:
            return None
        if (samples[-1].timestamp-samples[0].timestamp).total_seconds() < self.min_span_seconds:
            return None
        for previous,current in zip(samples,samples[1:]):
            gap = (current.timestamp-previous.timestamp).total_seconds()
            if not 0 < gap <= self.max_gap_seconds:
                return None
        return tuple(samples)
