"""Deterministic scenario demonstration, without MQTT or real-time waiting.

Run with: python -m examples.step3_simulation
"""

from src.domain import Patient, DiabetesProfile, HypertensionProfile, AnxietyProfile
from src.domain.parameters import HeartRate, BloodPressure
from src.simulation import SensorSimulator
from src.simulation.strategies import (
    NormalStrategy, ProgressiveAnomalyStrategy, SuddenAnomalyStrategy,
    MissingDataStrategy, RecoveryStrategy,
)


def build_simulators():
    first = Patient("P001", "Patient 1", profiles=[DiabetesProfile(), HypertensionProfile()])
    first.add_parameter(HeartRate())
    first.add_parameter(BloodPressure())
    second = Patient("P002", "Patient 2", profiles=[AnxietyProfile()])
    second.add_parameter(HeartRate())
    return [
        SensorSimulator(first, strategies={
            "heart_rate": NormalStrategy(80, 80),
            "systolic_bp": NormalStrategy(120, 120),
            "diastolic_bp": NormalStrategy(80, 80),
        }),
        SensorSimulator(second, strategies={"heart_rate": NormalStrategy(75, 75)}),
    ]


def show(label, simulators):
    print(f"\n--- {label} ---")
    for simulator in simulators:
        measurements = simulator.read()
        values = {m.parameter: m.value for m in measurements}
        print(f"{simulator.patient_id} | {simulator.status} | {values or 'aucune mesure'}")


def main():
    simulators = build_simulators()
    first, second = simulators
    for simulator in simulators:
        simulator.start()
    try:
        show("NORMAL", simulators)
        first.set_strategy("heart_rate", ProgressiveAnomalyStrategy(step=5))
        for cycle in range(1, 4):
            show(f"PROGRESSIF {cycle}", simulators)
        first.set_strategy("heart_rate", SuddenAnomalyStrategy(change=50))
        show("BRUTAL", simulators)
        show("BRUTAL : valeur maintenue", simulators)
        first.set_strategy("heart_rate", MissingDataStrategy())
        show("DONNÉE MANQUANTE : fréquence cardiaque P001", simulators)
        first.simulate_failure()
        show("PANNE : tout le capteur P001", simulators)
        first.restore()
        first.set_strategy("heart_rate", RecoveryStrategy(target_value=80, step=25))
        for cycle in range(1, 4):
            show(f"REPRISE {cycle}", simulators)
        second.patient.monitoring_enabled = False
        show("SURVEILLANCE DÉSACTIVÉE POUR P002", simulators)
    finally:
        for simulator in simulators:
            simulator.stop()
    show("ARRÊT", simulators)


if __name__ == "__main__":
    main()
