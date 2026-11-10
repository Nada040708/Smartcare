from .generation_strategy import GenerationStrategy
from .normal_strategy import NormalStrategy
from .progressive_strategy import ProgressiveStrategy
from .sudden_change_strategy import SuddenChangeStrategy
from .recovery_strategy import RecoveryStrategy
from .missing_data_strategy import MissingDataStrategy

# UML names; historical Python names remain valid.
ProgressiveAnomalyStrategy = ProgressiveStrategy
SuddenAnomalyStrategy = SuddenChangeStrategy

__all__ = [
    "GenerationStrategy",
    "NormalStrategy",
    "ProgressiveStrategy",
    "SuddenChangeStrategy",
    "RecoveryStrategy",
    "MissingDataStrategy",
    "ProgressiveAnomalyStrategy",
    "SuddenAnomalyStrategy",
]
