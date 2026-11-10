"""A technical event or monitoring-state transition, ready for step 11."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TechnicalEvent:
    event_id: str
    type: str
    description: str
    patient_id: str | None = None
    device_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = 'RECORDED'
    details: dict = field(default_factory=dict)
