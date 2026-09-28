import numpy as np
import pytest
from scipy.stats import t
from probabilistic_core import student_logpdf,prior_weights,fit_profiles,evaluate,calibrate_scales,scale_at


def test_normalized_student_and_uncertainty_penalty():
    x=np.array([0,1,100.])
    assert np.allclose(student_logpdf(x,3),t.logpdf(x,4,scale=3))
    assert student_logpdf(0,30)<student_logpdf(0,3)
    assert student_logpdf(10000,3)<student_logpdf(1000,3)
    assert np.exp(prior_weights(np.arange(-100,101)*.1,1)).sum()==pytest.approx(1)


def test_cfo_and_training_profiles_do_not_use_test_values():
    y=np.arange(8.)+100; p=np.zeros((3,8)); m=np.arange(8)<4
    a=fit_profiles(y,p,m,10);y[~m]+=999
    b=fit_profiles(y,p,m,10)
    assert np.array_equal(a['train'],b['train'])
    assert np.array_equal(a['offset'],b['offset'])
    assert not np.array_equal(a['test'],b['test'])


def test_shared_satellite_is_one_latent_and_exact_predictive_sum():
    g=np.array([-1.,0,1]);base={'train':np.array([-4.,0,-2]),'test':np.array([-1.,-2,-3]),'test_mse':np.array([1.,4,9]),'weight_s':1,'n_test':1,'satellite_id':'s'}
    rows=[dict(base,track_id=str(i)) for i in range(2)]
    out=evaluate(rows,g,g,np.array([0.]),None,{'s':1})
    lp=prior_weights(g,1);p=np.exp(lp+2*base['train']);p/=p.sum()
    assert out['conditional_predictive_log_score']==pytest.approx(np.log(p@np.exp(2*base['test'])))
    assert out['tracks'][0]['timing']==out['tracks'][1]['timing']
    independent=evaluate(rows,g,g,np.array([0.]),None,{'s':1},per_track=True)
    assert independent['conditional_predictive_log_score']!=pytest.approx(out['conditional_predictive_log_score'])


def test_scan_shift_grid_and_validation():
    g=np.arange(-2.,3);r={'track_id':'a','satellite_id':'s','train':np.array([-9,-4,-1,0,-1.]),'test':np.zeros(5),'test_mse':np.ones(5),'weight_s':1,'n_test':1}
    out=evaluate([r],g,np.array([-1.,0,1]),np.array([-1.,0,1]),1,{'s':.1})
    assert out['clock']['mean_s']>0
    assert out['conditional_predictive_log_score']==pytest.approx(0)
    with pytest.raises(ValueError):evaluate([r],g,g,g,1,{'s':1})


def test_age_bins_floor_and_fallback():
    rows=[{'age_hours':2.,'equivalent_tau_s':0.} for _ in range(60)]
    bins=calibrate_scales(rows)
    assert scale_at(2,bins)==.05
    assert bins[1]['pooled_fallback']


def test_evaluation_never_updates_reported_timing_posterior():
    g=np.array([-1.,0,1]);r={'track_id':'a','satellite_id':'s','train':np.array([-3.,0,-1.]),
        'test':np.array([-1.,-2,-3]),'test_mse':np.ones(3),'weight_s':1,'n_test':1}
    a=evaluate([r],g,g,np.array([0.]),None,{'s':1})
    r['test']=np.array([100.,-100,-100])
    b=evaluate([r],g,g,np.array([0.]),None,{'s':1})
    assert a['tracks'][0]['timing']==b['tracks'][0]['timing']
    assert a['conditional_predictive_log_score']!=b['conditional_predictive_log_score']


def test_grid_refinement_preserves_constant_predictive_density():
    for step in (1.,.1):
        g=np.arange(-3,3+step/2,step)
        r={'track_id':'a','satellite_id':'s','train':-g*g,'test':np.full(len(g),-7.),
           'test_mse':np.ones(len(g)),'weight_s':1,'n_test':1}
        out=evaluate([r],g,g,np.array([0.]),None,{'s':1})
        assert out['conditional_predictive_log_score']==pytest.approx(-7)
        assert out['clock']['edge_mass']==0
