from types import SimpleNamespace as C
from copy import deepcopy
import pytest
import evaluate as ev


def candidate(rank, cfo):
    return C(candidate_rank=rank,fractional_margin=.1,
             fractional_tracking_cfo_hz=cfo,integer_epoch_sample=0,
             fractional_epoch_offset_samples=0,passed_fractional_margin_gate=True)


def fixture():
    sid='s'
    ps=[C(visit_index=0,probe_index=0,receiver_id=rx,candidates=[candidate(0,rx*4000)]) for rx in (0,1)]
    raw=C(probes=ps,sample_rate_hz=2500000)
    projected=C(source_group_id='g',source_sample_start=0,source_sample_end=10,
                support_center_utc_ns=5,receiver_id=0,visit_index=0,probe_index=0,
                candidate_rank=0,candidate_id='candidate',channel=1,edge=C(value='lower'))
    row=dict(training=False,source_group_id='g',source_sample_start=0,source_sample_end=10,
             support_center_utc_ns=5,stream_id='rx-0',track_id='t',projected_observation_id='o',
             u_east=.5,u_up=.8,east_variance=.1,candidate_probabilities=[1.])
    branch=dict(session_id=sid,track_count=1,branch='truth_diagnostic',rows=[row])
    return [dict(session_id=sid,split='calibration')],{sid:raw},dict(branches=[branch]),projected


def test_endpoint_excludes_doppler_training_observations(monkeypatch):
    inventory,inputs,a,p=fixture()
    monkeypatch.setattr('leo.application.scanner_trajectory.project_scanner_candidates',lambda raw:[p])
    a['branches'][0]['rows'][0]['training']=True
    rows,accounting=ev.endpoint_rows(inventory,inputs,None,a,4000)
    assert rows==[]
    assert accounting[0]['counts']['excluded_doppler_training_observations']==1


def test_exact_provenance_join_and_ambiguous_exclusion(monkeypatch):
    inventory,inputs,a,p=fixture()
    monkeypatch.setattr('leo.application.scanner_trajectory.project_scanner_candidates',lambda raw:[p])
    rows,_=ev.endpoint_rows(inventory,inputs,None,a,4000)
    assert len(rows)==1 and rows[0]['matched']
    assert rows[0]['split']=='cal' and rows[0]['east']==.5
    p2=deepcopy(p);p2.candidate_id='other-candidate'
    monkeypatch.setattr('leo.application.scanner_trajectory.project_scanner_candidates',lambda raw:[p,p2])
    rows,accounting=ev.endpoint_rows(inventory,inputs,None,a,4000)
    assert rows==[] and accounting[0]['counts']['ambiguous_provenance']==1


def test_one_candidate_cannot_be_scored_in_two_tracks(monkeypatch):
    inventory,inputs,a,p=fixture()
    monkeypatch.setattr('leo.application.scanner_trajectory.project_scanner_candidates',lambda raw:[p])
    a['branches'][0]['rows'].append(dict(a['branches'][0]['rows'][0],track_id='other'))
    with pytest.raises(ValueError,match='multiple scored tracks'):
        ev.endpoint_rows(inventory,inputs,None,a,4000)


def test_exact_public_point_link_resolves_same_support_modes(monkeypatch):
    inventory,inputs,a,p=fixture()
    p2=deepcopy(p);p2.candidate_id='other-candidate';p2.candidate_rank=1
    monkeypatch.setattr('leo.application.scanner_trajectory.project_scanner_candidates',lambda raw:[p,p2])
    inventory[0].update(input_manifest_sha256='capture',analysis_manifest_sha256='analysis')
    links={'s':dict(input_manifest_sha256='capture',analysis_manifest_sha256='analysis',
                    rows=[dict(track_id='t',observation_id='o',candidate_ids=['candidate'])])}
    rows,_=ev.endpoint_rows(inventory,inputs,None,a,4000,links)
    assert len(rows)==1 and rows[0]['matched']
    links['s']['input_manifest_sha256']='bad'
    with pytest.raises(ValueError,match='digest'):
        ev.endpoint_rows(inventory,inputs,None,a,4000,links)


def test_association_inventory_fails_closed():
    inventory=[dict(session_id='s',ready=True,split='holdout',input_manifest_sha256='capture',analysis_manifest_sha256='analysis')]
    manifest=dict(sessions=[dict(pose=dict(session_id='s',pose_authority=dict(latitude_deg=1.,longitude_deg=2.)))])
    branch=dict(session_id='s',split='holdout',branch='truth_diagnostic',site=dict(latitude_deg=1.,longitude_deg=2.,diagnostic_truth=True),rows=[],input_manifest_sha256='capture',analysis_manifest_sha256='analysis')
    ev.validate_associations(dict(branches=[branch]),inventory,manifest)
    with pytest.raises(ValueError,match='exactly'):
        ev.validate_associations(dict(branches=[]),inventory,manifest)
    bad=deepcopy(branch);bad['site']['longitude_deg']=3.
    with pytest.raises(ValueError,match='location'):
        ev.validate_associations(dict(branches=[bad]),inventory,manifest)
