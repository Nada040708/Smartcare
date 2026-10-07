from src.domain.measurement import Measurement


class DataValidator:
    """
    Validates incoming physiological measurements.
    """

    def validate(self, measurement: Measurement) -> bool:
        return (
            measurement.validate()
            and self.validate_format(measurement)
            and self.validate_range(measurement)
        )

    def validate_format(self, measurement: Measurement) -> bool:
        if not isinstance(measurement, Measurement):
            return False

        if not isinstance(measurement.values, dict):
            return False

        for parameter, value in measurement.values.items():
            if not isinstance(parameter, str):
                return False

            if not isinstance(value, (int, float)):
                return False

        return True

    def validate_range(self, measurement: Measurement) -> bool:
        ranges = {
            "heart_rate": (30.0, 220.0),
            "spo2": (70.0, 100.0),
            "temperature": (30.0, 45.0),
        }

        for parameter, value in measurement.values.items():
            if parameter in ranges:
                minimum, maximum = ranges[parameter]

                if not minimum <= value <= maximum:
                    return False

        return True