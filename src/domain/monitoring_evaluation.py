"""Internal rule observations; absence of an anomaly is not evidence of recovery."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    status: str  # MATCHED, CLEAR, UNKNOWN
    fresh: bool
    result: dict | None


@dataclass(frozen=True)
class MonitoringEvaluation:
    source_id: str
    sequence: int
    patient_id: str
    timestamp: datetime
    enabled: bool
    rules: tuple[RuleEvaluation, ...]

    @property
    def anomalies(self):
        return [r.result for r in self.rules if r.status == 'MATCHED' and r.fresh]
