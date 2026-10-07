from src.domain.measurement import Measurement


class AnomalyDetector:
    """
    Detects physiological anomalies in measurements.
    """

    def detect(self, measurement: Measurement) -> list[dict]:
        anomalies = []

        values = measurement.values

        if "heart_rate" in values and values["heart_rate"] > 100:
            anomalies.append({
                "parameter": "heart_rate",
                "type": "high_heart_rate",
                "value": values["heart_rate"],
                "message": "Heart rate is above the normal range.",
            })

        if "spo2" in values and values["spo2"] < 95:
            anomalies.append({
                "parameter": "spo2",
                "type": "low_spo2",
                "value": values["spo2"],
                "message": "SpO2 is below the normal range.",
            })

        if "temperature" in values and values["temperature"] > 37.5:
            anomalies.append({
                "parameter": "temperature",
                "type": "high_temperature",
                "value": values["temperature"],
                "message": "Temperature is above the normal range.",
            })

        combined_anomaly = self.detect_combined_anomaly(measurement)

        if combined_anomaly is not None:
            anomalies.append(combined_anomaly)

        return anomalies

    def detect_combined_anomaly(
        self,
        measurement: Measurement,
    ) -> dict | None:

        values = measurement.values

        heart_rate_high = (
            "heart_rate" in values
            and values["heart_rate"] > 100
        )

        spo2_low = (
            "spo2" in values
            and values["spo2"] < 95
        )

        if heart_rate_high and spo2_low:
            return {
                "parameter": "heart_rate + spo2",
                "type": "combined_cardiopulmonary_anomaly",
                "value": {
                    "heart_rate": values["heart_rate"],
                    "spo2": values["spo2"],
                },
                "message": "High heart rate combined with low SpO2.",
            }

        return None