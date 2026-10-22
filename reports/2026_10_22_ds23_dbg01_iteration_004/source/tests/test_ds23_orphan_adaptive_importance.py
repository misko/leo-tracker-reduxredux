import numpy as np
import pytest
from scipy.special import logsumexp

from ds23_orphan_adaptive_importance import gaussian_importance


def test_importance_weights_reproduce_exact_conjugate_gaussian_evidence():
    y=2.;sigma=.5
    variance=1/(1+1/sigma**2);mean=variance*y/sigma**2
    proposals=[dict(mean=np.array([mean]),root=np.array([[np.sqrt(variance)]]),weight=1.)]
    draws,weight=gaussian_importance(proposals,8,31)
    log_likelihood=-.5*((y-draws[:,0])/sigma)**2-np.log(sigma)-.5*np.log(2*np.pi)
    actual=logsumexp(log_likelihood+weight)-np.log(len(draws))
    expected=-.5*y*y/(1+sigma*sigma)-.5*np.log(2*np.pi*(1+sigma*sigma))
    assert actual==pytest.approx(expected,abs=1e-12)


def test_prior_proposal_has_exact_unit_importance_weights():
    proposals=[dict(mean=np.zeros(3),root=np.eye(3),weight=1.)]
    z,w=gaussian_importance(proposals,7,4)
    np.testing.assert_allclose(w,0.,atol=1e-14)
    assert z.shape==(128,3)
