import json
import pytest

from evaluate_three_recorded_scans import verify_iq, candidate_points, native_glrt_parity


def test_iq_requires_independent_hash_and_event_agreement(tmp_path):
    visits=tmp_path/'visits';visits.mkdir()
    event={'visit_index':0,'target':{'channel':1}}
    row={'visit':0,'event':event,'raw_sha256':'a'*64,'size_bytes':2400000}
    receipt={'visit':0,'source':{'event':event,'raw_sha256':'a'*64,'raw_bytes':2400000}}
    path=visits/'visit-000000.json';path.write_text(json.dumps(receipt))
    assert verify_iq(tmp_path,[row],[event])['passed']
    receipt['source']['raw_sha256']='b'*64;path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match='authority mismatch'):verify_iq(tmp_path,[row],[event])


def test_iq_missing_visit_is_not_success(tmp_path):
    (tmp_path/'visits').mkdir()
    with pytest.raises(ValueError,match='incomplete'):verify_iq(tmp_path,[],[{}])


def test_point_conversion_keeps_source_cfo_and_gate():
    points=candidate_points([[[1,0,2,30,100.,200.,.1,.05,.05,1]]],
                            [{'valid_start_counter':2**53,'target':{'channel':4}}])
    assert points==[dict(visit=0,time=0,rx=1,rank=2,channel=4,epoch=30,acquired_cfo=100.,cfo=200.,margin=.05,passing=True)]


def test_native_glrt_parity_preserves_decisions_despite_tolerance():
    policy={'native_glrt_cfo_absolute_tolerance_hz':1e-9,'native_glrt_score_absolute_tolerance':1e-12}
    a=[[[0,0,0,30,100.,100.,.1,.05,.025,1]]]
    b=[[a[0][0].copy()]];b[0][0][6]+=1e-16
    assert native_glrt_parity(a,b,policy)['passed']
    b[0][0][8]-=1e-16
    assert not native_glrt_parity(a,b,policy)['passed']
    b[0][0][8]=.025;b[0][0][3]=31
    assert not native_glrt_parity(a,b,policy)['passed']


def test_native_boolean_completion_serializes_to_integer_port(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import evaluate_three_recorded_scans as e
    calls=[]
    def run(argv,**kwargs):
        calls.append(kwargs['input'])
        return SimpleNamespace(stdout='' if '--checkpoint' in argv else 'unavailable\n')
    monkeypatch.setattr(e.subprocess,'run',run)
    (tmp_path/'detector.stdout').write_text(json.dumps({'candidates':[[0,0,0,30,100.,100.,.1,.05,.05,True]]})+'\n{}\n')
    e.host_projection(tmp_path,{'session_id':'s','manifest_sha256':'digest'},
        [['2500000','0','123','1','0','0','0','0','1','0','11200000000','0','capture','analysis','1']],
        tmp_path,compare_to_arm=False)
    assert len(calls)==2
    assert all(text.split()[-1]=='1' for text in calls)
