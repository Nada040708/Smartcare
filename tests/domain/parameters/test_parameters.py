from src.domain.parameters import (
    HeartRate,
    SpO2,
    Temperature,
)


def test_heart_rate():
    heart_rate = HeartRate()

    value = heart_rate.generate()

    assert 60.0 <= value <= 100.0
    assert heart_rate.get_value() == value
    assert heart_rate.is_normal()


def test_spo2():
    spo2 = SpO2()

    value = spo2.generate()

    assert 95.0 <= value <= 100.0
    assert spo2.get_value() == value
    assert spo2.is_normal()


def test_temperature():
    temperature = Temperature()

    value = temperature.generate()

    assert 36.0 <= value <= 37.5
    assert temperature.get_value() == value
    assert temperature.is_normal()


def test_parameter_metadata():
    heart_rate = HeartRate()

    metadata = heart_rate.get_metadata()

    assert metadata["name"] == "heart_rate"
    assert metadata["unit"] == "bpm"
    assert metadata["normal_min"] == 60.0
    assert metadata["normal_max"] == 100.0