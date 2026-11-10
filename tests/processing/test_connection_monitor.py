from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest

from src.domain import Measurement, Patient
from src.processing.connection_monitor import ConnectionMonitor, load_connection_policy


def policy(parameters=('heart_rate','glucose')):
    return {'timeout_seconds':10,'startup_grace_seconds':10,'devices':[
        {'patient_id':pid,'device_id':'SIM_'+pid,'parameters':list(parameters)} for pid in ('P001','P002')]}


def reading(clock, parameter='heart_rate', pid='P001', *, timestamp=None, value=None):
    return Measurement(str(uuid4()),pid,device_id='SIM_'+pid,parameter=parameter,
                       unit='bpm' if parameter=='heart_rate' else 'mg/dL',value=value or 80,
                       quality='valid',timestamp=timestamp or clock[0])


@pytest.fixture
def monitor():
    clock=[datetime(2026,10,9,14,tzinfo=timezone.utc)]
    patients={p:Patient(p,p) for p in ('P001','P002')}
    return ConnectionMonitor(policy(),patients,now=lambda:clock[0]),patients,clock


def test_never_seen_device_times_out_only_after_startup_grace(monitor):
    m,patients,clock=monitor
    assert m.evaluate(patients['P001'],[])[:2]==(True,False)
    clock[0]+=timedelta(seconds=10)
    connected,complete,events=m.evaluate(patients['P001'],[])
    assert not connected and not complete
    assert len(events)==1 and events[0].type=='DISCONNECTED' and events[0].status=='ACTIVE'
    assert m.evaluate(patients['P001'],[])[2]==[]
    assert m.snapshots('P002')[0]['status']=='WAITING'


def test_silence_recovery_needs_new_data_and_all_parameters(monitor):
    m,patients,clock=monitor
    measures=[reading(clock),reading(clock,'glucose')]
    assert m.evaluate(patients['P001'],measures)[:2]==(True,True)
    clock[0]+=timedelta(seconds=10)
    assert m.evaluate(patients['P001'],[])[:2]==(False,False)
    # Replays or newly received delayed data cannot resolve silence.
    assert m.evaluate(patients['P001'],measures)[:2]==(False,False)
    clock[0]+=timedelta(seconds=1)
    connected,complete,events=m.evaluate(patients['P001'],[reading(clock)])
    assert connected and not complete
    assert any(e.type=='DISCONNECTED' and e.status=='RESOLVED' for e in events)
    assert any(e.type=='RECOVERY' for e in events)
    clock[0]+=timedelta(seconds=1)
    connected,complete,events=m.evaluate(patients['P001'],[reading(clock),reading(clock,'glucose')])
    assert connected and complete
    assert any(e.type=='MISSING_DATA' and e.status=='RESOLVED' for e in events)
    assert m.snapshots('P001')[0]['status']=='CONNECTED'


def test_partial_data_does_not_mask_a_missing_parameter_or_create_duplicates(monitor):
    m,patients,clock=monitor
    m.evaluate(patients['P001'],[reading(clock),reading(clock,'glucose')])
    clock[0]+=timedelta(seconds=11)
    connected,complete,events=m.evaluate(patients['P001'],[reading(clock)])
    assert connected and not complete
    assert [e.type for e in events]==['MISSING_DATA']
    event_id=events[0].event_id
    clock[0]+=timedelta(seconds=1)
    assert m.evaluate(patients['P001'],[reading(clock)])[2]==[]
    assert m.snapshots('P001')[0]['episodes']['MISSING_DATA']['event_id']==event_id
    # Old glucose with a new message identity still cannot count as fresh data.
    old=reading(clock,'glucose',timestamp=clock[0]-timedelta(seconds=11))
    assert m.evaluate(patients['P001'],[old])[:2]==(True,False)


def test_restore_keeps_original_episode_and_timeout_across_restart(monitor):
    m,patients,clock=monitor
    m.evaluate(patients['P001'],[reading(clock),reading(clock,'glucose')])
    clock[0]+=timedelta(seconds=11)
    m.evaluate(patients['P001'],[])
    snapshots=m.snapshots()
    clock[0]+=timedelta(seconds=2)
    restored=ConnectionMonitor(policy(),patients,now=lambda:clock[0])
    restored.restore(snapshots)
    assert restored.evaluate(patients['P001'],[])==(False,False,[])
    assert restored.snapshots('P001')[0]['episodes']==snapshots[0]['episodes']


def test_disabled_patient_does_not_generate_incidents_and_devices_are_isolated(monitor):
    m,patients,clock=monitor
    patients['P001'].monitoring_enabled=False
    clock[0]+=timedelta(seconds=100)
    assert m.evaluate(patients['P001'],[])==(True,False,[])
    assert m.snapshots('P001')[0]['status']=='PAUSED'
    assert m.evaluate(patients['P002'],[])[:2]==(False,False)
    assert not m.snapshots('P001')[0]['episodes']


def test_unregistered_device_or_parameter_is_refused(monitor):
    m,patients,clock=monitor
    measurement=reading(clock)
    measurement.device_id='UNREGISTERED'
    with pytest.raises(ValueError):
        m.evaluate(patients['P001'],[measurement])


@pytest.mark.parametrize('change', [
    {'timeout_seconds':0}, {'timeout_seconds':True}, {'startup_grace_seconds':float('nan')},
    {'devices':[{'patient_id':'P001','device_id':'X','parameters':['unknown']}]},
    {'devices':[{'patient_id':'P001','device_id':'X','parameters':[]}]},
])
def test_invalid_policy_rejected(tmp_path,change):
    p=policy();p.update(change)
    path=tmp_path/'policy.json';path.write_text(json.dumps(p))
    with pytest.raises(ValueError):
        load_connection_policy(path)
