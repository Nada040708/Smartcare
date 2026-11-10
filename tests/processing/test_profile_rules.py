from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.domain import Patient, Measurement, DiabetesProfile, HypertensionProfile, AnxietyProfile
from src.domain.clinical_profile import ClinicalProfile
from src.domain.monitoring_rule import ThresholdRule, CombinedRule, TrendRule, Condition
from src.domain.parameter_definitions import PARAMETER_DEFINITIONS
from src.processing import AnomalyDetector, DataValidator, AlertEngine


class Clock:
    def __init__(self):
        self.current = datetime(2026,10,8,16,tzinfo=timezone.utc)
    def __call__(self):
        return self.current
    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def setup():
    clock=Clock()
    return clock, AnomalyDetector(validator=DataValidator(now=clock))


def sample(clock, parameter, value, patient='P001', device='SIM_01', offset=0, **kwargs):
    return Measurement(str(uuid4()),patient,device_id=device,parameter=parameter,value=value,
                       unit=PARAMETER_DEFINITIONS[parameter].unit,
                       timestamp=clock()+timedelta(seconds=offset),quality='valid',**kwargs)


def ids(results):
    return {r['rule_id'] for r in results}


def stress_samples(clock, activity=0.1, patient='P001', hrv_offset=0):
    return [sample(clock,'heart_rate',120,patient),sample(clock,'hrv',20,patient,offset=hrv_offset),
            sample(clock,'respiratory_rate',25,patient),sample(clock,'activity',activity,patient)]


def test_same_glucose_value_has_different_results_by_profile(setup):
    clock,detector=setup
    diabetic=Patient('P001','First',profiles=[DiabetesProfile()])
    anxiety=Patient('P002','Second',profiles=[AnxietyProfile()])
    assert ids(detector.detect(sample(clock,'glucose',220),diabetic)) == {'diabetes_glucose_high'}
    assert detector.detect(sample(clock,'glucose',220,'P002'),anxiety) == []


def test_multiple_profiles_accumulate_rules_and_evidence(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[DiabetesProfile(),HypertensionProfile()])
    results=detector.detect_batch([sample(clock,'glucose',60),sample(clock,'systolic_bp',150)],patient)
    assert ids(results)=={'diabetes_glucose_low','hypertension_systolic_high'}
    glucose=next(r for r in results if r['rule_id']=='diabetes_glucose_low')
    assert glucose['severity']=='CRITICAL'
    assert glucose['profile_ids']==['diabetes']
    assert glucose['evidence'][0]['unit']=='mg/dL'


@pytest.mark.parametrize('op,value,matched', [('>',100,False),('>=',100,True),('<',100,False),('<=',100,True),('==',100,True),('>',101,True)])
def test_exact_threshold_operators(setup,op,value,matched):
    clock,_=setup
    rule=ThresholdRule(rule_id='custom',severity='WARNING',message='Demo',parameter='heart_rate',operator=op,threshold=100)
    profile=ClinicalProfile('custom','Custom','Demo',['heart_rate'],rules=[rule])
    detector=AnomalyDetector(validator=DataValidator(now=clock),common_rules=[])
    result=detector.detect(sample(clock,'heart_rate',value),Patient('P001','First',profiles=[profile]))
    assert bool(result) is matched


def test_stress_pattern_requires_all_inputs_and_rest_context(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[AnxietyProfile()])
    first=stress_samples(clock)
    assert 'anxiety_rest_pattern' not in ids(detector.detect_batch(first[:3],patient))
    results=detector.detect(first[3],patient)
    assert ids(results)=={'anxiety_rest_pattern'}
    assert len(results[0]['evidence'])==4
    assert 'sans diagnostic' in results[0]['message']
    clock.advance(1)
    assert 'anxiety_rest_pattern' not in ids(detector.detect(sample(clock,'activity',0.8),patient))


@pytest.mark.parametrize('offset',[-11,-31])
def test_combination_rejects_excessive_skew_or_old_context(setup,offset):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[AnxietyProfile()])
    assert 'anxiety_rest_pattern' not in ids(detector.detect_batch(stress_samples(clock,hrv_offset=offset),patient))


def test_context_never_crosses_patient_boundary(setup):
    clock,detector=setup
    first=Patient('P001','First',profiles=[AnxietyProfile()])
    second=Patient('P002','Second',profiles=[AnxietyProfile()])
    detector.detect_batch(stress_samples(clock)[:3],first)
    assert detector.detect(sample(clock,'activity',0.1,'P002'),second)==[]
    with pytest.raises(ValueError,match='mismatch'):
        detector.detect(sample(clock,'heart_rate',120,'P002'),first)


def test_trend_needs_multiple_samples_time_span_and_net_increase(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[HypertensionProfile()])
    for value in [110,120]:
        assert 'hypertension_systolic_rising' not in ids(detector.detect(sample(clock,'systolic_bp',value),patient))
        clock.advance(5)
    result=detector.detect(sample(clock,'systolic_bp',130),patient)
    trend=next(r for r in result if r['kind']=='TrendRule')
    assert [m['value'] for m in trend['evidence']]==[110,120,130]


@pytest.mark.parametrize('values,seconds,devices', [
    ([110,110,150],[0,5,5],['A','A','A']),
    ([110,120,130],[0,1,1],['A','A','A']),
    ([110,120,130],[0,40,5],['A','A','A']),
    ([110,120,130],[0,5,5],['A','B','A']),
])
def test_trend_rejects_step_burst_gap_or_mixed_devices(setup,values,seconds,devices):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[HypertensionProfile()])
    for value,delta,device in zip(values,seconds,devices):
        clock.advance(delta)
        assert 'hypertension_systolic_rising' not in ids(detector.detect(sample(clock,'systolic_bp',value,device=device),patient))


def test_duplicate_ids_and_readings_do_not_create_more_results(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[DiabetesProfile()])
    m=sample(clock,'glucose',200)
    assert detector.detect(m,patient)
    assert detector.detect(m,patient)==[]
    m.measurement_id=str(uuid4())
    assert detector.detect(m,patient)==[]  # same logical reading with a new message ID
    m.value=210
    with pytest.raises(ValueError,match='reading_id'):
        detector.detect(m,patient)


def test_reused_message_id_with_changed_data_is_rejected(setup):
    clock,detector=setup
    patient=Patient('P001','First')
    m=sample(clock,'heart_rate',120)
    detector.detect(m,patient)
    m.value=130
    with pytest.raises(ValueError,match='measurement_id'):
        detector.detect(m,patient)


def test_late_samples_do_not_replace_recent_state(setup):
    clock,detector=setup
    patient=Patient('P001','First')
    detector.detect(sample(clock,'heart_rate',80),patient)
    assert detector.detect(sample(clock,'heart_rate',140,offset=-1),patient)==[]
    assert detector.detect(sample(clock,'heart_rate',140),patient)==[]


def test_invalid_batch_does_not_partially_update_history(setup):
    clock,detector=setup
    patient=Patient('P001','First')
    valid=sample(clock,'heart_rate',120)
    bad=sample(clock,'spo2',90);bad.quality='questionable'
    with pytest.raises(ValueError):
        detector.detect_batch([valid,bad],patient)
    assert detector.detect(valid,patient)  # still new, not consumed by failed batch


def test_expiry_and_disabled_monitoring_clear_combination_context(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[AnxietyProfile()])
    detector.detect_batch(stress_samples(clock)[:3],patient)
    clock.advance(121)
    assert detector.detect(sample(clock,'activity',0.1),patient)==[]
    clock.advance(1)
    detector.detect_batch(stress_samples(clock)[:3],patient)
    patient.monitoring_enabled=False
    assert detector.detect(sample(clock,'activity',0.1),patient)==[]
    patient.monitoring_enabled=True
    assert detector.detect(sample(clock,'activity',0.1),patient)==[]


def test_same_rule_in_multiple_profiles_is_evaluated_once(setup):
    clock,_=setup
    rule=ThresholdRule(rule_id='shared',severity='WARNING',message='Demo',parameter='heart_rate',operator='>',threshold=100)
    profiles=[ClinicalProfile(p,p,'',['heart_rate'],rules=[rule]) for p in ['first','second']]
    detector=AnomalyDetector(validator=DataValidator(now=clock),common_rules=[])
    result=detector.detect(sample(clock,'heart_rate',120),Patient('P001','First',profiles=profiles))
    assert len(result)==1 and result[0]['profile_ids']==['first','second']
    profiles[1].rules=[ThresholdRule(rule_id='shared',severity='CRITICAL',message='Different',parameter='heart_rate',operator='>',threshold=150)]
    with pytest.raises(ValueError,match='Conflicting'):
        detector.detect(sample(clock,'heart_rate',120),Patient('P001','First',profiles=profiles))


def test_same_reading_constraint_for_a_paired_custom_rule(setup):
    clock,_=setup
    rule=CombinedRule(rule_id='pair',severity='WARNING',message='Demo',conditions=(Condition('systolic_bp','>',140),Condition('diastolic_bp','>',90)),same_reading=True)
    patient=Patient('P001','First',profiles=[ClinicalProfile('custom','Custom','',[],rules=[rule])])
    detector=AnomalyDetector(validator=DataValidator(now=clock),common_rules=[])
    assert detector.detect_batch([sample(clock,'systolic_bp',150),sample(clock,'diastolic_bp',95)],patient)==[]
    clock.advance(1)
    result=detector.detect_batch([sample(clock,'systolic_bp',150,reading_id='PAIR'),sample(clock,'diastolic_bp',95,reading_id='PAIR')],patient)
    assert ids(result)=={'pair'}


def test_raw_payload_is_validated_before_metadata_reconstruction(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[DiabetesProfile()])
    data=sample(clock,'glucose',200).to_dict()
    data['ieee11073_metadata']['metric_code']='fabricated'
    with pytest.raises(ValueError):
        detector.detect_payload(data,patient)
    data['ieee11073_metadata']['metric_code']=None
    assert ids(detector.detect_payload(data,patient))=={'diabetes_glucose_high'}


def test_rule_severity_and_provenance_reach_alerts_with_unique_ids(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[DiabetesProfile()])
    result=detector.detect(sample(clock,'glucose',60),patient)
    first=AlertEngine().evaluate('P001',result)[0]
    second=AlertEngine().evaluate('P001',result)[0]
    assert first.severity=='CRITICAL'
    assert first.rule_id=='diabetes_glucose_low'
    assert first.profile_ids==['diabetes']
    assert first.measurement_ids==[result[0]['evidence'][0]['measurement_id']]
    assert first.alert_id != second.alert_id
    with pytest.raises(ValueError,match='mismatch'):
        AlertEngine().evaluate('P002',result)


def test_removing_a_profile_changes_rules_on_the_next_reading(setup):
    clock,detector=setup
    patient=Patient('P001','First',profiles=[DiabetesProfile()])
    assert detector.detect(sample(clock,'glucose',220),patient)
    patient.remove_profile(DiabetesProfile())
    clock.advance(1)
    assert detector.detect(sample(clock,'glucose',220),patient)==[]


def test_history_is_bounded_and_clear_patient_releases_it(setup):
    clock,_=setup
    detector=AnomalyDetector(validator=DataValidator(now=clock),max_history=3)
    patient=Patient('P001','First')
    for value in range(80,90):
        detector.detect(sample(clock,'heart_rate',value),patient)
        clock.advance(1)
    assert len(detector._history['P001'])==3
    assert len(detector._seen['P001'])==3
    detector.clear_patient('P001')
    assert 'P001' not in detector._history
    assert 'P001' not in detector._seen


@pytest.mark.parametrize('fields', [
    {'parameter':'unknown'}, {'operator':'execute'}, {'threshold':float('nan')}, {'severity':'INVALID'},
])
def test_bad_threshold_configuration_is_rejected(fields):
    config=dict(rule_id='custom',severity='WARNING',message='Demo',parameter='heart_rate',operator='>',threshold=100)
    config.update(fields)
    with pytest.raises(ValueError):
        ThresholdRule(**config)
