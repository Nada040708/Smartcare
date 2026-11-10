from unittest.mock import patch

import pytest

from src.simulation.strategies import (
    NormalStrategy, ProgressiveStrategy, SuddenChangeStrategy,
    RecoveryStrategy, MissingDataStrategy, ProgressiveAnomalyStrategy, SuddenAnomalyStrategy,
)


def test_normal_strategy_requires_explicit_parameter_bounds():
    strategy = NormalStrategy(60, 100)
    with patch("src.simulation.strategies.normal_strategy.random.uniform", return_value=1.0):
        assert strategy.generate(80) == 81
        assert strategy.generate(100) == 100
        assert strategy.generate(20) == 60


def test_progressive_strategy_supports_rising_and_falling_values():
    assert ProgressiveStrategy(step=2).generate(80) == 82
    assert ProgressiveStrategy(step=-5).generate(80) == 75


def test_rounding_does_not_escape_a_narrow_normal_interval():
    strategy = NormalStrategy(0.04, 0.06)
    with patch("src.simulation.strategies.normal_strategy.random.uniform", return_value=1.0):
        assert 0.04 <= strategy.generate(0.05) <= 0.06


def test_sudden_strategy_jumps_only_once_and_can_be_reset():
    strategy = SuddenChangeStrategy(change=65, trigger_after=2)
    value = 80
    values = []
    for _ in range(5):
        value = strategy.generate(value)
        values.append(value)
    assert values == [80, 80, 145, 145, 145]
    strategy.reset()
    assert strategy.generate(80) == 80


def test_recovery_approaches_target_without_overshoot():
    strategy = RecoveryStrategy(target_value=80, step=7)
    assert strategy.generate(90) == 83
    assert strategy.generate(83) == 80
    assert strategy.generate(79) == 80
    assert strategy.generate(80) == 80


def test_missing_data_is_absence_not_zero():
    assert MissingDataStrategy().generate(80) is None


def test_uml_names_are_available():
    assert ProgressiveAnomalyStrategy is ProgressiveStrategy
    assert SuddenAnomalyStrategy is SuddenChangeStrategy


@pytest.mark.parametrize("factory", [
    lambda: NormalStrategy(100, 60), lambda: NormalStrategy(float("nan"), 100),
    lambda: ProgressiveStrategy(float("inf")), lambda: ProgressiveStrategy(True),
    lambda: SuddenChangeStrategy(trigger_after=-1), lambda: SuddenChangeStrategy(trigger_after=True),
    lambda: SuddenChangeStrategy(change=float("nan")),
    lambda: RecoveryStrategy(80, step=0), lambda: RecoveryStrategy(80, step=-2),
])
def test_invalid_strategy_configuration_is_rejected(factory):
    with pytest.raises(ValueError):
        factory()
