from types import SimpleNamespace
import copy
import numpy as np
import pytest
from predictive_graph_bundle import append_bundle,polynomial_pair,member_evidence
from leo.analysis.research.retained_track_likelihood import PERIOD


def fixture():
    tracks=[]
    for k in range(2):
        t=np.arange(1+k,45,2,dtype=float)
        tracks.append(dict(key=str(k),receiver=1,channel=7,rf_hz=12e9,times=t,
            values=500+3*t+.4*t*t+PERIOD*k,observation_ids=[f'{k}-{x}' for x in t],pieces=['old polynomial']))
    return SimpleNamespace(tracks=tracks,white=['a','b'],rx_basis=[np.c_[t['times'],t['times']**2] for t in tracks],curved=np.array([0,1]))


def test_alias_aligned_union_preserves_measurements_and_original_calibration():
    scan=fixture();original=copy.deepcopy(scan);members=[dict(track_id='a',track_index=0,alias_lift=0),dict(track_id='b',track_index=1,alias_lift=-1)]
    changed,i=append_bundle(scan,members,set(),'union');track=changed.tracks[i]
    assert len(scan.tracks)==2 and changed.curved is scan.curved and changed.tracks[0] is scan.tracks[0]
    assert changed.white[:2]==scan.white and 'pieces' not in track
    for k,m in enumerate(members):
        selected=track['bundle_member_indices']==k
        np.testing.assert_array_equal(track['times'][selected],scan.tracks[k]['times'])
        np.testing.assert_allclose(track['values'][selected],scan.tracks[k]['values']+m['alias_lift']*PERIOD,atol=1e-8)
        np.testing.assert_array_equal(changed.rx_basis[i][selected],scan.rx_basis[k])
        np.testing.assert_array_equal(scan.tracks[k]['values'],original.tracks[k]['values'])


@pytest.mark.parametrize('problem',['occupied','mixed_lane','duplicate_id','same_timestamp','fractional_alias'])
def test_union_refuses_duplicate_owned_or_incompatible_measurements(problem):
    scan=fixture();members=[dict(track_index=0,alias_lift=0),dict(track_index=1,alias_lift=-1)];occupied=set()
    if problem=='occupied':occupied.add(scan.tracks[0]['observation_ids'][0])
    if problem=='mixed_lane':scan.tracks[1]['channel']=8
    if problem=='duplicate_id':scan.tracks[1]['observation_ids'][0]=scan.tracks[0]['observation_ids'][0]
    if problem=='same_timestamp':scan.tracks[1]['times'][0]=scan.tracks[0]['times'][0]
    if problem=='fractional_alias':members[1]['alias_lift']=-.5
    with pytest.raises(ValueError):append_bundle(scan,members,occupied,'union')


def test_pair_nomination_corrects_only_integer_alias_and_penalizes_extra_degree():
    a,b=fixture().tracks;r=polynomial_pair(a,b)
    assert r['alias_lift']==-1 and r['degree']==1  # The declared 150 Hz floor penalizes unsupported extra coefficients.
    assert r['RMS_hz']<150
    np.testing.assert_allclose(r['aligned_values_hz'][len(a['times']):],b['values']-PERIOD)


def test_member_veto_prevents_strong_parent_from_hiding_ambiguous_short_member():
    target=dict(members=[dict(track_id='long'),dict(track_id='short')])
    def proposal(norad,short):
        return dict(norad=norad,arms={a:dict(bundle_member_scores={
            'long':dict(negative_twice_log_density=0 if norad==1 else 100,rms_hz=30,held_points=8),
            'short':dict(negative_twice_log_density=short,rms_hz=30,held_points=4)}) for a in ('c0','fitted_c')})
    folds=[dict(seed=1,proposals=[proposal(1,10),proposal(2,12)])]
    assert not member_evidence(folds,target,1)['passed']
    folds[0]['proposals'][1]=proposal(2,30)
    assert member_evidence(folds,target,1)['passed']


def test_bundle_replay_enforces_support_source_hash_and_current_ownership(tmp_path):
    import json
    from predictive_graph_bundle import bundle_context,validated_bundle_context
    scan=fixture();p=SimpleNamespace(members=[],slices=[],keep=np.array([],bool))
    d=dict(scan=scan,problems={a:(p,None) for a in ('c0','fitted_c')},entries=[])
    inv=dict(job=dict(job_id='job'),tracks=[dict(track_id='a',track_index=0),dict(track_id='b',track_index=1)],
             policy={a:dict(proposed_associated_ids=[]) for a in ('c0','fitted_c')})
    source=tmp_path/'source.json';source.write_text(json.dumps(dict(bundles=[dict(bundle_id='bundle',job=inv['job'],source_hashes={},
        members=[dict(track_id='a',track_index=0,alias_lift=0),dict(track_id='b',track_index=1,alias_lift=-1)])])))
    _,target=bundle_context(d,inv,source,'bundle');validation=tmp_path/'validation';validation.mkdir()
    (validation/'protocol.json').write_text(json.dumps(dict(job=inv['job'],target=target)))
    result=dict(track_id='bundle',graph_bundle=True,annotation=dict(status='conditionally_supported_identity'),bundle_member_checks=dict(passed=True))
    (validation/'result.json').write_text(json.dumps(result));_,replayed=validated_bundle_context(d,inv,validation)
    assert replayed==target
    result['bundle_member_checks']['passed']=False;(validation/'result.json').write_text(json.dumps(result))
    with pytest.raises(ValueError,match='member-specific'):validated_bundle_context(d,inv,validation)
    result['bundle_member_checks']['passed']=True;(validation/'result.json').write_text(json.dumps(result))
    inv['policy']['fitted_c']['proposed_associated_ids']=[target['observation_ids'][0]]
    with pytest.raises(ValueError,match='owns'):validated_bundle_context(d,inv,validation)
    inv['policy']['fitted_c']['proposed_associated_ids']=[];source.write_text(source.read_text()+'\n')
    with pytest.raises(ValueError,match='discovery changed'):validated_bundle_context(d,inv,validation)


def test_alias_marginalization_is_invariant_to_integer_representation_shift():
    from audit_bundle_split_identity import aliased_prediction
    observed=np.array([10.,11.,12.]);means=np.array([[10.,11.,12.]])
    covariance=np.eye(3)[None]*100;lp=np.zeros(1);train=np.array([True,False,False]);held=~train
    first=aliased_prediction(observed,means,covariance,lp,train,held,[-1,0,1])
    shifted=aliased_prediction(observed+PERIOD,means,covariance,lp,train,held,[-2,-1,0])
    assert first['negative_twice_log_density']==pytest.approx(shifted['negative_twice_log_density'])
    np.testing.assert_allclose(first['held_residual_hz'],shifted['held_residual_hz'])
