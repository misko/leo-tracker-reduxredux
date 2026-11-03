import json
import pytest

from evaluate_three_recorded_scans import verify_iq, candidate_points


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
