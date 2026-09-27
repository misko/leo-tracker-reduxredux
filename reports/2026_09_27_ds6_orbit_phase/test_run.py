import numpy as np
from run import cfo_evidence,phase_evidence

def test_cfo_offset_integral_matches_dense_gaussian():
    residual=np.array([512000.,512045.,511970.,512010.]);n=len(residual)
    covariance=100.**2*np.eye(n)+1e12*np.ones((n,n))
    _,det=np.linalg.slogdet(covariance)
    expected=-.5*(n*np.log(2*np.pi)+det+residual@np.linalg.solve(covariance,residual))
    assert abs(cfo_evidence(residual)-expected)<1e-6

def test_constant_phase_offset_cannot_determine_position():
    y=np.array([.1,.2,.3]);g=np.array([[.2,.3,.4],[1.2,1.3,1.4]])
    score=phase_evidence(y,g,np.ones(3))
    np.testing.assert_allclose(score[0],score[1],atol=1e-12)
    np.testing.assert_allclose(phase_evidence(y+2,g,np.ones(3)),score,atol=1e-12)

def test_one_dwell_has_no_phase_information_with_free_offset():
    score=phase_evidence(np.array([1.]),np.array([[0.],[2.],[3.]]),np.ones(1))
    np.testing.assert_allclose(score,0.,atol=1e-12)
