from src.simulation.strategies import (
    NormalStrategy,
    ProgressiveStrategy,
    SuddenChangeStrategy,
)


def test_normal_strategy():
    strategy = NormalStrategy()

    current_value = 80.0
    new_value = strategy.generate(current_value)

    assert 79.0 <= new_value <= 81.0


def test_progressive_strategy():
    strategy = ProgressiveStrategy(step=2.0)

    current_value = 80.0
    new_value = strategy.generate(current_value)

    assert new_value == 82.0


def test_sudden_change_strategy():
    strategy = SuddenChangeStrategy(change=15.0)

    current_value = 80.0
    new_value = strategy.generate(current_value)

    assert new_value == 95.0