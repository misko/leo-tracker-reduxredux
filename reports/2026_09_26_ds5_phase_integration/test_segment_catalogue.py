import numpy as np
import json
from pathlib import Path
from segment_catalogue_trial import block_residuals,components
from segment_phase_trial import options_from_evidence,predictive
from scipy.special import logsumexp
from segment_uncertainty import common_offset_evidence
from catalogue_trial import constant_log_evidence

def test_episode_boundary_keeps_identical_block_coverage():
    times=np.array([1.1,1.3,1.8,2.1,2.8,3.1]);episodes=np.array([0,0,1,1,1,1]);mask=np.array([1,1,1,0,0,1],bool);raw=np.arange(6.)[None,None,:]
    tr,mt=block_residuals(raw,times,mask,episodes);te,mh=block_residuals(raw,times,~mask,episodes)
    assert mt==[(0,1),(1,1),(1,3)] and mh==[(1,2)]
    np.testing.assert_allclose(tr,[[[.5,2.,5.]]]);np.testing.assert_allclose(te,[[[3.5]]])
    parts=list(components(tr,te,mt,mh))
    np.testing.assert_array_equal(parts[0][1],np.concatenate([p[1] for p in parts[1:]],axis=-1))
    np.testing.assert_array_equal(parts[0][2],np.concatenate([p[2] for p in parts[1:]],axis=-1))

def test_supplied_episode_evidence_matches_exact_predictive_sum():
    bank=dict(candidate_ids=['a','b'],logprior=np.log([[.4,.6],[.4,.6]]),projection=np.zeros((2,2,3)))
    tr=np.log([[1,2],[3,4]]);joint=tr+np.log([[5,6],[7,8]])
    opts=options_from_evidence(bank,tr,joint)
    assert np.isclose(predictive(opts),logsumexp(joint+bank['logprior'])-logsumexp(tr+bank['logprior']))

def test_real_banks_preserve_every_block_and_candidate_alignment():
    root=Path(__file__).resolve().parent/'segment-catalogue'
    for fold in (0,1):
        banks={name:dict(np.load(root/f'f{fold}-{name}.npz')) for name in ('whole','before','after')}
        for name in ('before','after'):
            np.testing.assert_array_equal(banks['whole']['indices'],banks[name]['indices'])
        for field in ('train_residual','held_residual'):
            np.testing.assert_array_equal(banks['whole'][field],np.concatenate([banks['before'][field],banks['after'][field]],axis=-1))
        assert banks['whole']['train_residual'].shape[-1]+banks['whole']['held_residual'].shape[-1]==38

def test_known_joint_time_is_not_independently_refitted_by_episode():
    # Each episode individually prefers a different orbital-time hypothesis.
    # Sharing one physical orbit time must penalize that disagreement.
    lp=np.log([.5,.5]);first=np.log([.99,.01]);second=np.log([.01,.99])
    shared=logsumexp(first+second+lp)
    independent=logsumexp(first+lp)+logsumexp(second+lp)
    assert shared<independent-3

def test_unequal_noise_offset_integral_matches_covariance_oracle():
    a=np.array([1.,4.,2.]);b=np.array([-2.,3.]);v=np.r_[np.full(3,4.),np.full(2,25.)];y=np.r_[a,b]
    cov=np.diag(v)+49*np.ones((5,5))
    expected=-.5*(5*np.log(2*np.pi)+np.linalg.slogdet(cov)[1]+y@np.linalg.solve(cov,y))
    assert np.isclose(common_offset_evidence(a,b,2.,5.,7.),expected)
    assert np.isclose(common_offset_evidence(a,b,5.,5.),constant_log_evidence(y,5.))

def test_real_phase_comparisons_preserve_matching_cfo_uncertainty_baseline():
    root=Path(__file__).resolve().parent/'segment-catalogue'
    ordinary=json.loads((root/'phase-results.json').read_text())['experiments']
    followup=json.loads((root/'phase-scale-only-results.json').read_text())['experiments']
    ablation=json.loads((root/'uncertainty-ablation.json').read_text())['results']
    assert len(ordinary)==6 and len(followup)==2
    for fold in (0,1):
        baseline=next(r for r in ordinary if r['fold']==fold and r['arm']=='continuous_identity_and_offset')
        changed=next(r for r in followup if r['fold']==fold)
        shared=next(r for r in ablation if r['fold']==fold and r['arm']=='shared_offset_shared_scale')
        separate=next(r for r in ablation if r['fold']==fold and r['arm']=='shared_offset_separate_scales')
        assert np.isclose(changed['total_cfo_held']-baseline['total_cfo_held'],separate['mode0_held_log_predictive']-shared['mode0_held_log_predictive'])
        assert baseline['kappa']==changed['kappa']
