import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.special import logsumexp
from empirical_prior import fit_prior,logpdf,cdf,quantile,discrete_weights
from timing_model import evaluate

REPORTS=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(REPORTS/'2026_09_26_reno_track_audit'))
from probabilistic_core import evaluate as old_evaluate,prior_weights


def rows():
    return [{'equivalent_tau_s':float(x),'age_hours':18.,'satellite_id':i%25,'validation_group':False}
            for i,x in enumerate(np.linspace(-3,1,100))]


def test_prior_excludes_validation_and_preserves_signed_bias():
    r=rows();m=fit_prior(r)
    assert quantile(m,18,.5)<-.5
    r[0]['validation_group']=True
    with pytest.raises(ValueError,match='validation'):fit_prior(r)


def test_density_cdf_and_quantile_normalization():
    m=fit_prior(rows());x=np.linspace(-100,100,100001)
    assert np.trapezoid(np.exp(logpdf(m,18,x)),x)==pytest.approx(1,abs=1e-4)
    assert cdf(m,18,[-1e8,1e8]).tolist()==pytest.approx([0,1])
    for q in (.01,.5,.99):assert cdf(m,18,[quantile(m,18,q)])[0]==pytest.approx(q)


def test_grid_weights_report_omitted_mass_and_young_fallback():
    m=fit_prior(rows());g=np.linspace(-2,2,41);lp,missing=discrete_weights(m,18,g)
    assert logsumexp(lp)==pytest.approx(0)
    assert missing>.1
    assert np.isfinite(logpdf(m,2,g)).all()
    assert m['bins'][0]['local_weight']==0


def test_explicit_prior_evaluator_matches_original_and_does_not_fit_on_test():
    total=np.arange(-3.,4);delta=np.arange(-2.,3);clock=np.array([-1.,0.,1.]);p={'s':prior_weights(delta,1)}
    r={'track_id':'a','satellite_id':'s','weight_s':3,'n_test':4,
       'train':-total**2,'test':-(total-1)**2,'test_mse':total**2+1}
    a=evaluate([r],total,delta,clock,1,p);b=old_evaluate([r],total,delta,clock,1,{'s':1})
    assert a['negative_log_score_per_test_observation']==pytest.approx(b['negative_log_score_per_test_observation'])
    assert a['tracks']==b['tracks']
    r['test']=100*total
    c=evaluate([r],total,delta,clock,1,p)
    assert a['tracks']==c['tracks'] and a['clock']==c['clock']


def test_rare_historical_component_is_not_lost_in_body_fit():
    r=rows()
    r.extend({'equivalent_tau_s':float(v),'age_hours':18.,'satellite_id':i,'validation_group':False}
             for i,v in enumerate((50,60,70,80)))
    model=fit_prior(r)
    assert 1-cdf(model,18,[40])[0]>.01
