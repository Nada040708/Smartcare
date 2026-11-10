from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class Consent:
    patient_id: str
    granted: bool = False
    consent_id: str = field(default_factory=lambda: str(uuid4()))
    date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not isinstance(self.granted, bool) or not self.patient_id or self.date.utcoffset() is None:
            raise ValueError('Consent requires an identity, a boolean and an aware timestamp')

    def revoke(self):
        self.granted = False
        self.date = datetime.now(timezone.utc)
