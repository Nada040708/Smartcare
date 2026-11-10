import main

from src.domain import Measurement


def test_offline_main_preserves_combined_detection_for_the_current_cycle(monkeypatch, capsys):
    readings = [
        Measurement("M1", "P001", device_id="SIM_P001", parameter="heart_rate", value=145, unit="bpm"),
        Measurement("M2", "P001", device_id="SIM_P001", parameter="spo2", value=90, unit="%"),
    ]
    monkeypatch.setattr(main.SensorSimulator, "read", lambda self: readings)
    main.main(["--storage", "memory", "--no-mqtt", "--cycles", "1"])
    output = capsys.readouterr().out
    assert "'measurements_count': 2" in output
    assert "'active_alerts_count': 3" in output
    assert "CRITICAL" in output
    assert "Monitoring stopped." in output


def test_offline_main_generates_structured_measurements_over_two_cycles(capsys):
    main.main(["--storage", "memory", "--no-mqtt", "--cycles", "2", "--interval", "0.001"])
    output = capsys.readouterr().out
    assert "'measurements_count': 14" in output
    assert output.count("P001 | systolic_bp:") == 2
    assert output.count("P001 | diastolic_bp:") == 2
    assert "Monitoring stopped." in output
