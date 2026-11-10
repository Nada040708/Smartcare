"""Partial 11073-10101 nomenclature mapping, not a 11073 transport stack.

Sources and unmapped parameters are documented in docs/step2_measurements.md.
No MDC code is inferred from a display unit or invented for a local metric.
"""

from dataclasses import asdict, dataclass
from datetime import datetime


# Full decimal MDC codes (including the partition), not bare term identifiers.
VERIFIED_MDC_MAPPINGS = {
    "spo2": ("150456", "MDC_PULS_OXIM_SAT_O2", "262688", "MDC_DIM_PERCENT"),
    "systolic_bp": ("150021", "MDC_PRESS_BLD_NONINV_SYS", "266016", "MDC_DIM_MMHG"),
    "diastolic_bp": ("150022", "MDC_PRESS_BLD_NONINV_DIA", "266016", "MDC_DIM_MMHG"),
}


@dataclass(frozen=True)
class IEEE11073Metadata:
    metric_code: str | None
    metric_refid: str | None
    unit_code: str | None
    unit_refid: str | None
    device_type: str
    timestamp: datetime
    quality: str
    mapping_status: str
    nomenclature_system: str = "urn:iso:std:iso:11073:10101"

    @classmethod
    def for_parameter(
        cls, parameter: str, timestamp: datetime, quality: str, device_type: str,
    ) -> "IEEE11073Metadata":
        mapping = VERIFIED_MDC_MAPPINGS.get(parameter)
        return cls(
            *(mapping or (None, None, None, None)),
            device_type=device_type,
            timestamp=timestamp,
            quality=quality,
            mapping_status="mapped" if mapping else "unmapped",
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
