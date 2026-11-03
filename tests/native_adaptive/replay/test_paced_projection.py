import pytest

from leo.native_pipeline.paced_projection import project_paced,analysis_identity


def test_analysis_identity_is_configuration_scoped():
    assert analysis_identity('a'*64)==analysis_identity('a'*64)
    assert analysis_identity('a'*64)!=analysis_identity('b'*64)
    with pytest.raises(ValueError):analysis_identity('invalid')


def fixture():
    capture={'receipt':{'plan':{'geometry':{'sample_rate_hz':2500000,'receiver_ids':[0,1]}},
        'events':[{'visit_index':0,'valid_start_counter':100,'valid_end_counter_exclusive':300100,
            'target':{'channel':1,'edge':'lower','rf_center_hz':11200000000},'actual_if_offset_hz':0}]},
        'timing':{'session_start_device_sample_counter':100,'first_sample_estimate_utc_ns':1000000000}}
    candidate=[0,0,0,722,-100,-100,.4,.1,.3,1]
    rows=[{'sequence':0,'accepted':True,'status':0,'candidates':[candidate]},
          {'kind':'summary','arrivals':1,'completed':1,'failed':0,'rejected':0}]
    return capture,rows


def test_run_identity_changes_ids_but_preserves_source_and_measurements():
    capture,rows=fixture()
    a=project_paced(capture,rows,'capture','run-a')[0]
    b=project_paced(capture,rows,'capture','run-b')[0]
    assert a.observation[0]!=b.observation[0]
    assert a.observation[1:]==b.observation[1:]
    assert a.source[2:]==(0,0,0,0,'integer','arm-ungated')


@pytest.mark.parametrize('change',['drop','missing','rank','probe','rate'])
def test_incomplete_or_wrong_geometry_is_rejected(change):
    capture,rows=fixture()
    if change=='drop':rows[-1]['rejected']=1
    if change=='missing':rows.pop(0)
    if change=='rank':rows[0]['candidates'][0][2]=1
    if change=='probe':rows[0]['candidates'][0][1]=1
    if change=='rate':capture['receipt']['plan']['geometry']['sample_rate_hz']=2000000
    with pytest.raises(ValueError):project_paced(capture,rows,'capture','analysis')
