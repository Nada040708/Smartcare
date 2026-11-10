import pytest

from src.demo import scenario_readings, private_password, prepare_secrets
from src.security.demo import initialize_demo_admin
from src.web.patients import load_patients


def test_regular_mode_never_accesses_store_or_password_prompt():
    def forbidden():raise AssertionError('No automatic bootstrap in normal mode')
    assert not initialize_demo_admin(forbidden,prompt=forbidden)


def test_scenarios_keep_other_patients_and_use_real_measurements():
    patients=load_patients()
    normal=scenario_readings(patients,0,'normal')
    anomaly=scenario_readings(patients,0,'anomaly')
    assert len(normal)==len(anomaly)==27
    assert all(m.validate() for m in normal+anomaly)
    assert next(m.value for m in anomaly if m.patient_id=='P001' and m.parameter=='glucose')==240
    assert [(m.patient_id,m.parameter,m.value) for m in normal if m.patient_id!='P001']==[(m.patient_id,m.parameter,m.value) for m in anomaly if m.patient_id!='P001']
    silent=scenario_readings(patients,1,'disconnection',elapsed=20,timeout=10)
    assert {m.patient_id for m in silent}=={'P002','P003'}
    assert len(scenario_readings(patients,2,'disconnection',elapsed=31,timeout=10))==27


def test_incomplete_existing_secrets_are_never_replaced(tmp_path):
    directory=tmp_path/'private';directory.mkdir();key=directory/'storage.key';key.write_bytes(b'existing-key')
    with pytest.raises(ValueError,match='incomplète'):prepare_secrets(directory)
    assert key.read_bytes()==b'existing-key'


def test_invalid_environment_password_is_not_printed_or_saved(monkeypatch,tmp_path,capsys):
    import src.demo as demo
    monkeypatch.setattr(demo,'ROOT',tmp_path)
    monkeypatch.setenv('SMARTCARE_DEMO_ADMIN_PASSWORD','bad')
    with pytest.raises(ValueError):private_password()
    assert not (tmp_path/'.env').exists()
    assert 'bad' not in capsys.readouterr().out


def test_interactive_password_is_requested_once_preserving_other_settings(monkeypatch,tmp_path,capsys):
    from types import SimpleNamespace
    import src.demo as demo
    calls=[]
    monkeypatch.setattr(demo,'ROOT',tmp_path)
    monkeypatch.setenv('SMARTCARE_DEMO_ADMIN_PASSWORD','')
    monkeypatch.setattr(demo.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    password='Temporary-test-password'
    monkeypatch.setattr(demo,'getpass',lambda message:(calls.append(message) or password))
    (tmp_path/'.env').write_text('POSTGRES_PORT=5433\n')
    assert private_password()==private_password()==password
    assert len(calls)==1
    assert 'POSTGRES_PORT=5433' in (tmp_path/'.env').read_text()
    assert password not in capsys.readouterr().out
