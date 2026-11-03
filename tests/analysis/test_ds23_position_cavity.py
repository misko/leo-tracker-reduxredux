import numpy as np
from scipy.special import logsumexp
from ds23_position_cavity import normal_grid,reweight_nodes,mixture_score


def test_position_grid_preserves_correlated_gaussian_moments_and_common_calibration():
    mean=np.array([.4,-.2]);cov=np.array([[.16,.06],[.06,.25]])
    g=normal_grid(mean,cov,[-12.5,-12.5],[12.5,12.5]);w=np.exp(g['log_weights']);x=g['positions'];delta=x-mean
    np.testing.assert_allclose(w@x,mean,atol=1e-14)
    np.testing.assert_allclose(delta.T@(delta*w[:,None]),cov,atol=1e-14)
    # A calibration mean changes with position. Conditional mixtures must
    # retain this anticorrelation instead of treating the two effects as independent.
    radio_response=np.array([-.9,.1]);geometry=np.array([1.,.2]);conditional_variance=.03
    predictions=x@(radio_response+geometry)
    variance=conditional_variance+w@((predictions-w@predictions)**2)
    expected=conditional_variance+(geometry+radio_response)@cov@(geometry+radio_response)
    assert abs(variance-expected)<1e-14
    independent=conditional_variance+geometry@cov@geometry+radio_response@cov@radio_response
    assert abs(independent-expected)>.1


def test_gaussian_other_family_density_cancels_importance_correction():
    mean=np.array([.3,-.5]);cov=np.array([[.2,.03],[.03,.4]])
    g=normal_grid(mean,cov,[-12.5,-12.5],[12.5,12.5]);d=g['positions']-mean
    loss=321.+np.einsum('ni,ij,nj->n',d,np.linalg.inv(cov),d)
    actual=reweight_nodes(g['positions'],mean,cov,g['log_weights'],loss)
    np.testing.assert_allclose(actual,g['log_weights'],atol=3e-14)


def test_truncated_grid_and_mixture_keep_one_common_normalization():
    g=normal_grid([12.4,0.],np.diag([1.,.5]),[-12.5,-12.5],[12.5,12.5])
    assert len(g['positions'])<9 and np.all(g['positions']<=12.5)
    assert abs(np.exp(g['log_weights']).sum()-1)<1e-14
    scores=np.arange(len(g['positions'])*2,dtype=float).reshape(-1,2)
    expected=-2*logsumexp(g['log_weights'][:,None]-scores/2,axis=0)
    np.testing.assert_allclose(mixture_score(scores,g['log_weights']),expected)
    assert abs(mixture_score(np.full(len(scores),1200.),g['log_weights'])-1200)<1e-12
