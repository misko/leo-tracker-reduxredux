from pathlib import Path
import json
import numpy as np
from joint_phase import masks,extract
from joint_phase_run import build
from joint_phase_score import shift_geometry
from timing_trial import evaluate
from shared_baseline_trial import baseline_posterior
from test_timing_trial import option

HERE=Path(__file__).resolve().parent

def test_three_sample_sets_are_disjoint_and_exhaustive():
    sets,_=masks();assert [int(s.sum()) for s in sets]==[35000,17400,17600]
    assert np.all(np.sum(np.array(sets),axis=0)==1)

def test_evaluation_iq_cannot_change_qualification_or_fitted_rate():
    scan=next(s for s in json.loads((HERE/'long-overlap/plan.json').read_text())['scans'] if s['selected'])
    old=json.loads((HERE/'long-overlap'/(scan['session_id']+'.json')).read_text())['rows'];designs,controls=build(scan['selected'][0],old,0)
    signal=np.column_stack([sum(designs[rx][m].sum(axis=1)*np.exp(1j*rx*(.7 if m==0 else -.5)) for m in (0,1)) for rx in (0,1)])
    a=extract(designs,controls,signal);sets,_=masks();changed=signal.copy();rng=np.random.default_rng(9);changed[sets[2]]+=100*(rng.normal(size=changed[sets[2]].shape)+1j*rng.normal(size=changed[sets[2]].shape));b=extract(designs,controls,changed)
    assert a['metrics']==b['metrics']
    assert [r['frequency_hz'] for r in a['modes']]==[r['frequency_hz'] for r in b['modes']]
    # A finite-noise single-source case must not become a second qualified mode.
    single=np.column_stack([designs[rx][0].sum(axis=1)*np.exp(.7j*rx) for rx in (0,1)])
    power=np.mean(abs(single)**2);noise=np.sqrt(power/2)*(rng.normal(size=single.shape)+1j*rng.normal(size=single.shape))
    result=extract(designs,controls,single+noise)
    assert result['modes'][0]['qualified'] and not result['modes'][1]['qualified']

def test_phase_epoch_shift_preserves_linear_geometry():
    tau=np.array([-.2,0,.2]);projection=np.stack([2*tau+1,-3*tau],axis=-1)[None,:,:]
    shifted=shift_geometry(dict(taus=tau,projection=projection),[-.0525,.05])['projection'][0]
    assert np.allclose(shifted[:,0],2*(tau-.0525)+1)
    assert np.allclose(shifted[:,1],-3*(tau+.05))

def test_known_sources_recover_phase_and_reject_absent_mode():
    for sid in ('scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3'):
        data=json.loads((HERE/'joint-phase'/(sid+'.json')).read_text());assert len(data['rows'])==108
        for example in data['synthetic']:
            for m in example['result']['modes']:
                present=example['source']=='both' or example['source']==m['mode']
                assert m['qualified']==present
                if present:
                    target=.7 if m['mode']==0 else -.5
                    assert abs(np.angle(np.exp(1j*(m['evaluation']['phase_rad']-target))))<.01
                    assert abs(m['frequency_hz']-example['residual_hz'])<1

def test_shared_baseline_is_neutral_without_phase_support():
    a=[option('a',[[0,.1,.2,.3]],-.5)];b=[option('b',[[0,.2,.4,.6]],-.2)];y=np.array([.1,.2,.4,.5]);f=np.full(4,11.2e9);train=np.array([1,0,1,0],bool)
    lp=baseline_posterior(a,b,y,np.zeros(4),f,f)
    assert np.allclose(np.exp(lp),1/81)
    result=evaluate(a,b,y,train,f,f,np.zeros(4),baseline_log_prior=np.linspace(-5,5,81))
    assert abs(result['cfo_gain'])<1e-12 and result['maximum_probability_change']<1e-12

def test_supported_slots_remain_in_real_score_and_donor_is_other_scan():
    for sid in ('scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3'):
        data=json.loads((HERE/'joint-phase'/(sid+'-scores.json')).read_text())
        assert len(data['experiments'])==16
        for observations in data['observation_sets']:
            assert len(observations['visits'])==len(observations['kappa'])==18
            if 'qualified' in observations['arm']:
                assert all(bool(k)==bool(n) for k,n in zip(observations['kappa'],observations['window_counts']))
        transferred=json.loads((HERE/'joint-phase'/(sid+'-baseline-scores.json')).read_text())
        assert transferred['protocol']['target_scan']==sid
        assert transferred['protocol']['donor_scan']!=sid
        assert all(np.isclose(sum(p['probabilities']),1) for p in transferred['donor_priors'])
