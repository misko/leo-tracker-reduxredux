"""Scientific checks for scale learning and circular uncertainty integration."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.special import i0
from scipy.stats import t

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('uncertainty_run',HERE/'run.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def banks():
    rng=np.random.default_rng(32)
    return [dict(y=np.array([.3,.1,.5,.4]),mask=np.array([True,False,True,False]),
        geometry=rng.normal(size=(3,4,4)),cfo_train=rng.normal(size=(3,4)),cfo_joint=rng.normal(size=(3,4))-5.) for _ in range(2)]


def test_mad_scale_matches_student_distribution_and_offset_invariance():
    # Deterministic quantiles remove sampling luck from the distribution test.
    residual=240*t.ppf((np.arange(10000)+.5)/10000,4)
    assert abs(module.estimate_scale(residual)-240)<.1
    assert abs(module.estimate_scale(residual+70000)-240)<.1


def test_circular_offset_integral_matches_direct_quadrature():
    y=np.array([-.2,.1,.7]);p=np.array([[[.1,-.1,.3]]]);kappa=np.array([.1,1.,20.])
    alpha=np.linspace(-np.pi,np.pi,20001)[:-1]
    direct=[np.log(np.mean(np.exp((k*np.cos(y-p[0,0]-alpha[:,None])-np.log(i0(k))).sum(axis=-1)))) for k in kappa]
    np.testing.assert_allclose(module.phase_score(y,p,kappa)[:,0,0],direct,atol=1e-11)
    assert np.all(np.isfinite(module.phase_score(y,p,np.array([10000.]))))


def test_kappa_one_reproduces_previous_independent_offset_model():
    sys.path.insert(0,str(HERE.parent/'2026_09_27_ds6_common_rate_validation'))
    from geometry import score_banks
    data=banks();old=score_banks(data);new=module.score_banks(data,np.array([1.]),np.array([1.]))
    for key in old:np.testing.assert_allclose(new[key],old[key],atol=1e-12)


def test_marginalized_uncertainty_does_not_learn_from_held_phase():
    original=banks();changed=[dict(b,y=b['y']+np.where(b['mask'],0.,1.8)) for b in original]
    kappa=np.geomspace(.1,1000.,41);weights=np.ones(41)/41
    a=module.score_banks(original,kappa,weights);b=module.score_banks(changed,kappa,weights)
    for key in ['training_log_evidence','held_cfo_log_predictive','phase_time_posterior','kappa_posteriors']:
        np.testing.assert_array_equal(a[key],b[key])
    assert a['held_phase_log_predictive']!=b['held_phase_log_predictive']


def test_response_only_cannot_update_candidate_or_time_weights():
    data=banks();kappa=np.geomspace(.1,1e4,129);weights=np.ones(129)/129
    r=module.score_banks(data,kappa,weights,geometry=False)
    np.testing.assert_allclose(r['held_cfo_log_predictive'],r['cfo_only_held_log_predictive'],atol=1e-12)
    np.testing.assert_allclose(r['phase_time_posterior'],r['cfo_only_time_posterior'],atol=1e-12)
    for p in r['kappa_posteriors']:np.testing.assert_allclose(sum(p),1.,atol=1e-12)


def test_saved_scales_use_training_residuals_and_bind_sources():
    result=json.loads((HERE/'results.json').read_text())
    assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
    for scan in result['scans']:
        path=HERE.parent/'2026_09_27_ds6_common_rate_validation'/(scan['session_id']+'-plan.json')
        assert scan['source_plan_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
        tracks={t['track_id']:t for t in json.loads(path.read_text())['tracks']}
        for audit in scan['track_audits']:
            tr=tracks[audit['track_id']]
            assert audit['training_mask']==tr['training_mask']
            assert audit['times_s']==tr['times_s']
            residual=np.array(audit['old_residual_hz']);mask=np.array(audit['training_mask'])
            expected=module.estimate_scale(residual[mask])
            np.testing.assert_allclose(expected,audit['learned_student_t_scale_hz'],rtol=1e-10)
            residual[~mask]+=1e8
            assert module.estimate_scale(residual[mask])==expected


def test_real_data_quadrature_is_resolved():
    summary=json.loads((HERE/'summary.json').read_text())
    for scan in summary['scans']:
        for arm,fields in scan['quadrature'].items():
            assert all(abs(value)<1e-4 for value in fields.values()),(scan['session_id'],arm,fields)
