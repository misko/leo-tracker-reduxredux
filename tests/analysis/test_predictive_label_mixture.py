import numpy as np
import pytest
from predictive_label_mixture import mixture_score,candidate_set


def test_mixture_is_normalized_not_best_label_selection_and_alias_count_does_not_increase_prior():
    r=mixture_score([10.,10.],np.log([.5,.5]));assert r['negative_twice_log_density']==pytest.approx(10.)
    np.testing.assert_allclose(r['weights'],[.5,.5])
    dominant=mixture_score([10.,100.],np.log([.5,.5]));assert dominant['negative_twice_log_density']==pytest.approx(10+2*np.log(2))
    aliases=mixture_score([10.,10.,10.],np.log([.25,.25,.5]));assert aliases['negative_twice_log_density']==pytest.approx(10.)
    assert sum(aliases['weights'][:2])==pytest.approx(aliases['weights'][2])


def test_candidates_require_paired_rf_evidence_and_preserve_alias_hypotheses():
    def proposal(n,score,alias=0,bad_fitted=False):
        return dict(norad=n,alias=alias,arms={a:dict(scores={'conditional_target':dict(negative_twice_log_density=score,rms_hz=100 if not bad_fitted or a=='c0' else 500)},
            final_phase_change_s=.001,minimum_target_elevation_deg=10) for a in ('c0','fitted_c')})
    folds=[dict(seed=1,proposals=[proposal(1,0),proposal(2,15),proposal(3,2,bad_fitted=True),proposal(4,50)]),
           dict(seed=2,proposals=[proposal(1,10,1),proposal(2,0)])]
    rows,evidence=candidate_set(folds)
    assert rows==[dict(norad=1,aliases=[0,1]),dict(norad=2,aliases=[0])]
    assert all(r['eligible_norads']==[1,2] for r in evidence)


def test_shared_component_equals_joint_density_minus_incumbent_density(monkeypatch):
    from types import SimpleNamespace
    import predictive_label_mixture as module
    from leo.analysis.research.predictive_track import gaussian_log_density
    mean=np.array([20.,-10.]);prior=np.array([.1,.2]);design=np.array([[1.,2.],[2.,-1.]])
    calc=dict(coefficient=mean.copy(),features=design,noise_precision=np.ones(1),coefficient_prior_precision=prior)
    p=SimpleNamespace(curved_calculate=lambda x:calc,keep=np.array([True,True]),noise_groups=np.zeros(2,int),point_noise=np.ones(2)*5)
    h0=np.array([[1.,.4],[.5,1.]]);h1=np.array([[1.,-.5]])
    y0=np.array([5.,30.]);y1=np.array([80.]);sigma0=np.array([10.,12.]);sigma1=np.array([9.]);g0=np.zeros(2,int);g1=np.zeros(1,int)
    def geometry(problem,entries):
        old=entries==['old'];h=h0 if old else h1;y=y0 if old else y1;sigma=sigma0 if old else sigma1;g=g0 if old else g1
        return SimpleNamespace(q=np.ones(len(y)),h=h),y,sigma,g,[]
    monkeypatch.setattr(module,'linear_geometry',geometry)
    monkeypatch.setattr(module,'geometry_features',lambda view,x,z:dict(features=view.h,intercept=np.zeros(len(view.h))))
    actual=module.SharedComponent(dict(candidate_index=1)).evaluate(p,np.zeros(2),np.ones(1),['old'])
    cov=np.linalg.inv(np.diag(prior)+design.T@design/25);noise0=np.diag(2*sigma0**2)+300**2;noise1=np.diag(2*sigma1**2)+300**2
    cross=h0@cov@h1.T;total=np.block([[noise0+h0@cov@h0.T,cross],[cross.T,noise1+h1@cov@h1.T]])
    joint=gaussian_log_density(np.r_[y0-h0@mean,y1-h1@mean],total);old=gaussian_log_density(y0-h0@mean,noise0+h0@cov@h0.T)
    assert actual==pytest.approx(-2*(joint-old),abs=1e-9)
    np.testing.assert_array_equal(calc['coefficient'],mean)


def test_member_audit_cannot_refit_away_opposite_fragment_biases():
    from audit_soft_bundle_members import member_checks
    t=np.arange(40,dtype=float);residual=np.r_[np.full(20,100.),np.full(20,-100.)]
    c=dict(diagnostics=[dict(times_s=t,raw_residual_hz=residual,profile_bias_hz=0.)])
    rows=member_checks(c,np.r_[np.zeros(20,int),np.ones(20,int)],[dict(track_id='a'),dict(track_id='b')])
    assert all(not r['passed'] and r['noise']['mean_z']>3 for r in rows)
    np.testing.assert_array_equal(rows[0]['residual_hz'],np.full(20,100.))


def test_expanded_phase_domain_is_bounded_and_cannot_extrapolate_orbits():
    from predictive_new_family import integration_grid
    np.testing.assert_array_equal(integration_grid([20,100],[-40,340],15),[-15,0,15])
    grid=integration_grid([20,100],[-40,340],.1,30);assert len(grid)==601 and grid[0]==-30 and grid[-1]==30
    with pytest.raises(ValueError,match='orbit bank'):integration_grid([0,100],[-20,340],.1,30)
    with pytest.raises(ValueError,match='bounded'):integration_grid([20,100],[-40,340],.1,45)
