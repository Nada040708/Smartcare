import json
from pathlib import Path
import re
from datetime import datetime
from uuid import uuid5, NAMESPACE_URL

from src.domain import Patient, DiabetesProfile, HypertensionProfile, AnxietyProfile
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.domain.consent import Consent

DEFAULT_PATIENTS = Path(__file__).resolve().parents[2] / 'config/patients.json'
PROFILES = {'diabetes': DiabetesProfile, 'hypertension': HypertensionProfile, 'anxiety': AnxietyProfile}
LABELS = {
    'heart_rate': 'Fréquence cardiaque', 'spo2': 'Saturation en oxygène',
    'temperature': 'Température', 'systolic_bp': 'Pression systolique',
    'diastolic_bp': 'Pression diastolique', 'glucose': 'Glycémie',
    'respiratory_rate': 'Fréquence respiratoire', 'hrv': 'Variabilité cardiaque', 'activity': 'Activité',
}


def load_patients(path=DEFAULT_PATIENTS):
    records = json.loads(Path(path).read_text())
    if not isinstance(records, list):
        raise ValueError('The patient registry must be a list')
    patients = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Invalid patient record')
        pid = record.get('patient_id')
        if not isinstance(pid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', pid) or pid in patients:
            raise ValueError('Invalid or duplicate patient identifier')
        name = record.get('name')
        profiles = record.get('profiles')
        enabled = record.get('monitoring_enabled', True)
        if not isinstance(name, str) or not name.strip() or not isinstance(enabled, bool):
            raise ValueError('Invalid patient name or monitoring flag')
        if not isinstance(profiles, list) or any(not isinstance(p, str) or p not in PROFILES for p in profiles):
            raise ValueError('Unknown clinical profile')
        patients[pid] = Patient(pid, name, monitoring_enabled=enabled,
                                profiles=[PROFILES[p]() for p in dict.fromkeys(profiles)])
        # Explicit, fictitious consent for the supplied simulated cohort only.
        configured = record.get('simulation_consent')
        if configured is not None:
            if not isinstance(configured, dict) or set(configured) != {'granted','date'}:
                raise ValueError('Invalid simulation consent')
            patients[pid].consent = Consent(pid,configured['granted'],str(uuid5(NAMESPACE_URL,'smartcare-demo:'+pid)),
                                            datetime.fromisoformat(configured['date']))
    return patients


def parameter_catalog():
    return {key: {'label': LABELS[key], 'unit': value.unit} for key, value in PARAMETER_DEFINITIONS.items()}


def profile_catalog():
    return [{'id': key, 'name': factory().name, 'description': factory().description}
            for key, factory in PROFILES.items()]


def patient_from_record(record):
    return Patient(record['patient_id'], record['name'],
                   monitoring_enabled=record['monitoring_enabled'],
                   profiles=[PROFILES[key]() for key in record['profiles']])


def merge_registered_patients(store, patients):
    """Merge database-managed patients into the shared live registry."""
    for record in store.connection.execute(
            'SELECT patient_id,name,profiles,monitoring_enabled FROM patient_registry ORDER BY patient_id'):
        patients[record['patient_id']] = patient_from_record(record)
    return patients
