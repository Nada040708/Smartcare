from datetime import timedelta

import pytest

from src.domain import ThresholdRule, Patient, MonitoringState
from src.processing import AnomalyDetector, DataValidator
from src.processing.connection_monitor import ConnectionMonitor
from src.processing.persistent_monitoring import PersistentMonitoring
from src.repositories.postgres_store import PostgresStore
from tests.processing.test_connection_monitor import policy, reading
from src.domain.consent import Consent

pytestmark=pytest.mark.postgres_integration


def session(store,clock,patients):
    detector=AnomalyDetector(DataValidator(now=lambda:clock[0]),common_rules=[ThresholdRule(
        rule_id='hr',parameter='heart_rate',operator='>',threshold=100,severity='WARNING',message='Test')])
    return PersistentMonitoring(store,detector=detector,restarted_at=clock[0],
        connection_monitor=ConnectionMonitor(policy(),patients,now=lambda:clock[0]))


def setup():
    from datetime import datetime,timezone
    return [datetime.now(timezone.utc)], {pid:Patient(pid,pid,consent=Consent(pid,True)) for pid in ('P001','P002')}


def test_atomic_timeout_recovery_restart_and_clinical_alert_preservation(postgres_schema):
    clock,patients=setup();patient=patients['P001']
    with PostgresStore(schema=postgres_schema) as store:
        s=session(store,clock,patients)
        s.process([reading(clock,value=140),reading(clock,'glucose')],patient)
        alert=s.alerts.getActive()[0]
        clock[0]+=timedelta(seconds=11)
        assert s.process([],patient)[1]==MonitoringState.DISCONNECTED
        assert s.alerts.getActive()[0].alert_id==alert.alert_id
        incidents=[e for e in s.events.getByPatient('P001') if e.type=='DISCONNECTED']
        assert len(incidents)==1 and incidents[0].status=='ACTIVE'
        incident_id=incidents[0].event_id
    with PostgresStore(schema=postgres_schema) as store:
        s=session(store,clock,patients)
        assert s.process([],patient)[1]==MonitoringState.DISCONNECTED
        assert len([e for e in s.events.getByPatient('P001') if e.type=='DISCONNECTED'])==1
        clock[0]+=timedelta(seconds=1)
        assert s.process([reading(clock),reading(clock,'glucose')],patient)[1]==MonitoringState.ALERT
        clock[0]+=timedelta(seconds=1)
        assert s.process([reading(clock),reading(clock,'glucose')],patient)[1]==MonitoringState.NORMAL
        assert not s.alerts.getActive()
        incidents=[e for e in s.events.getByPatient('P001') if e.type=='DISCONNECTED']
        assert incidents[0].status=='RESOLVED' and incidents[0].event_id==incident_id
        assert any(e.type=='RECOVERY' for e in s.events.getByPatient('P001'))


def test_missing_parameter_blocks_normal_without_hiding_new_anomalies(postgres_schema):
    clock,patients=setup();patient=patients['P001']
    with PostgresStore(schema=postgres_schema) as store:
        s=session(store,clock,patients)
        assert s.process([reading(clock),reading(clock,'glucose')],patient)[1]==MonitoringState.NORMAL
        clock[0]+=timedelta(seconds=11)
        assert s.process([reading(clock)],patient)[1]==MonitoringState.SURVEILLANCE
        from src.web.queries import DashboardQueries
        runtime={'running':True,'connected':True,'evaluated_at':clock[0].isoformat(),'states':{'P001':'SURVEILLANCE'}}
        displayed=DashboardQueries(store,patients,runtime,now=clock[0]).overview()['patients'][0]
        assert displayed['latest']['glucose']['stale'] is True
        assert displayed['devices'][0]['status']=='DEGRADED'
        clock[0]+=timedelta(seconds=1)
        assert s.process([reading(clock,value=140)],patient)[1]==MonitoringState.ALERT
        clock[0]+=timedelta(seconds=1)
        assert s.process([reading(clock)],patient)[1]==MonitoringState.ALERT
        assert s.alerts.getActive()[0].recovery_count==0


def test_sql_failure_rolls_back_connection_state_and_incidents(postgres_schema,monkeypatch):
    clock,patients=setup();patient=patients['P001']
    with PostgresStore(schema=postgres_schema) as store:
        s=session(store,clock,patients)
        s.process([reading(clock),reading(clock,'glucose')],patient)
        clock[0]+=timedelta(seconds=11)
        original=s.events.save
        def fail(event):
            if event.type=='DISCONNECTED':
                raise RuntimeError('write failure')
            return original(event)
        monkeypatch.setattr(s.events,'save',fail)
        with pytest.raises(RuntimeError):
            s.process([],patient)
        assert s.connections.snapshots('P001')[0]['status']=='CONNECTED'
        assert not [e for e in s.events.getByPatient('P001') if e.type=='DISCONNECTED']
        monkeypatch.setattr(s.events,'save',original)
        assert s.process([],patient)[1]==MonitoringState.DISCONNECTED


def test_duplicates_and_rejected_devices_cannot_clear_timeout(postgres_schema):
    clock,patients=setup();patient=patients['P001']
    with PostgresStore(schema=postgres_schema) as store:
        s=session(store,clock,patients)
        measurements=[reading(clock),reading(clock,'glucose')]
        s.process(measurements,patient)
        clock[0]+=timedelta(seconds=11)
        s.process([],patient)
        assert s.process(measurements,patient)[1]==MonitoringState.DISCONNECTED
        bad=reading(clock);bad.device_id='OTHER'
        with pytest.raises(ValueError):
            s.process([bad],patient)
        assert s.measurements.count()==2
