import copy
import hashlib
import json
from types import SimpleNamespace
import numpy as np
import pytest
from native_iq_refined_context import replacement_values,reject_unsupported_shared_refinement,refined_context,replay_refinement
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_refinement_preserves_alias_and_rejects_partial_or_mismatched_measurements():
    t=dict(observation_ids=['a','b'],times=[1,2],values=[10+PERIOD,20])
    rows=[dict(point=dict(observation_id=o,time_s=time,CFO_hz=y),methods=dict(joint_all=dict(CFO_hz=y+3,frequency_search_boundary=False))) for o,time,y in [('a',1,10),('b',2,20)]]
    np.testing.assert_allclose(replacement_values(t,rows,'joint_all'),[13+PERIOD,23])
    with pytest.raises(ValueError,match='complete native'):replacement_values(t,rows[:1],'joint_all')
    bad=copy.deepcopy(rows);bad[0]['point']['time_s']=2
    with pytest.raises(ValueError,match='time'):replacement_values(t,bad,'joint_all')
    bad=copy.deepcopy(rows);bad[0]['methods']['joint_all']['frequency_search_boundary']=True
    with pytest.raises(ValueError,match='boundary'):replacement_values(t,bad,'joint_all')


def test_shared_family_route_cannot_silently_discard_refined_measurements():
    reject_unsupported_shared_refinement({})
    with pytest.raises(ValueError,match='does not yet replay'):
        reject_unsupported_shared_refinement({'measurement_refinement':{'source':'refined.json'}})


def test_context_verifies_worker_evidence_and_preserves_original_scan(tmp_path):
    def save(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))
        return hashlib.sha256(path.read_bytes()).hexdigest()
    plan_hash=save(tmp_path/'plan.json',{'workers':1})
    panel_hash=save(tmp_path/'panel/manifest.json',{'plan_sha256':plan_hash,'raw_authority_matches_tracking':True})
    rows=[{'point':{'observation_id':'a','time_s':1,'CFO_hz':10},'methods':{'joint_all':{'CFO_hz':13}}}]
    worker=tmp_path/'worker.json'
    worker_hash=save(worker,{'rows':rows,'panel_manifest_sha256':panel_hash})
    save(tmp_path/'execution.json',[{'status':'complete'}])
    result={'rows':rows,'plan_sha256':plan_hash,'worker_hashes':{str(worker):worker_hash},
            'all_original_selected_points_present':True,'no_GPS_TLE_or_satellite_in_local_refinement':True}
    path=tmp_path/'result.json';save(path,result)
    track={'observation_ids':['a'],'times':[1],'values':np.array([10.]),'noise':150}
    d={'scan':SimpleNamespace(tracks=[track]),'entries':[],'problems':{}}
    changed,receipt=refined_context(d,{'track_index':0},path)
    assert changed['scan'] is not d['scan']
    assert d['scan'].tracks[0]['values'][0]==10
    assert changed['scan'].tracks[0]['values'][0]==13
    assert changed['scan'].tracks[0]['noise']==150
    assert replay_refinement(d,{'track_index':0},receipt)['scan'].tracks[0]['values'][0]==13
    with pytest.raises(ValueError,match='overlaps retained'):
        refined_context(dict(d,entries=[{'observation_ids':['a']}]),{'track_index':0},path)
    result['rows'][0]['methods']['joint_all']['CFO_hz']=99;save(path,result)
    with pytest.raises(ValueError,match='terminal worker'):
        refined_context(d,{'track_index':0},path)
