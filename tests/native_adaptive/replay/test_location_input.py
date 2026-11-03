import pytest
from leo.native_pipeline.location_input import graph_authority
from leo.native_pipeline.membership import Lane,Observation


def inputs():
    origin=1700000000000000000
    obs={'a':Observation('a','g',Lane(0,1,'lower',11.2e9),origin,origin+10000000,origin+20000000,1.)}
    support=[{'candidate_id':'a','source_start_counter':0,'source_end_counter':50000,
              'factorial_support_moments_s':[1.,0.,.00001,0.]}]
    receipt={'capture_digest':'capture'}
    meta={'capture_digest':'capture','start_utc_ns':origin,'session_id':'session',
          'knot_start_s':-60.,'knot_step_s':10.,'knot_count':43}
    return obs,support,receipt,meta


def test_support_authority_is_response_free():
    obs,s,r,m=inputs();text=graph_authority(obs,s,r,m)
    assert text.startswith('META\tsession\tcapture\t1700000000000000000\n')
    assert len(text.splitlines()[2].split('\t'))==8


def test_cross_capture_orbits_rejected():
    obs,s,r,m=inputs();m['capture_digest']='other'
    with pytest.raises(ValueError,match='different captures'):graph_authority(obs,s,r,m)


def test_wrong_epoch_rejected():
    obs,s,r,m=inputs();m['start_utc_ns']+=86400000000000
    with pytest.raises(ValueError,match='does not cover'):graph_authority(obs,s,r,m)


def test_duplicate_support_rejected():
    obs,s,r,m=inputs();s.append(s[0])
    with pytest.raises(ValueError,match='inventory'):graph_authority(obs,s,r,m)
