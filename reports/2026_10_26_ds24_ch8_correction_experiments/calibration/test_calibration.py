from types import SimpleNamespace
import numpy as np
from run import native_scan, prediction


def test_predictive_density_matches_full_covariance():
    rng = np.random.default_rng(881)
    u = rng.normal(size=(13,5)); a=rng.normal(size=(5,5)); gram=a@a.T+np.eye(5)
    sigma=rng.uniform(.5,2,size=13); raw=rng.normal(size=13)
    covariance=np.diag(sigma**2)+u@np.linalg.solve(gram,u.T)
    expected=raw@np.linalg.solve(covariance,raw)+np.linalg.slogdet(covariance)[1]+13*np.log(2*np.pi)
    result=prediction(raw,u,gram,sigma)
    assert abs(result['negative_twice_log_density']-expected)<1e-10


def test_native_design_has_common_hz_response_without_mutation():
    t=np.linspace(-1,1,9); basis=np.column_stack((t*t,t*t*t))
    scan=SimpleNamespace(tracks=[{'rf_hz':10e9},{'rf_hz':13e9}],rx_basis=[basis.copy(),basis.copy()])
    original=[b.copy() for b in scan.rx_basis]; transformed=native_scan(scan)
    a=np.array([3.,-7.])
    for k,track in enumerate(scan.tracks):
        assert np.allclose((track['rf_hz']/11.5e9)*transformed.rx_basis[k]@a,basis@a)
        assert np.array_equal(scan.rx_basis[k],original[k])
    assert transformed is not scan


def test_zero_shared_uncertainty_gives_independent_noise_density():
    raw=np.array([1.,2.,3.]); sigma=np.array([.5,1.,2.])
    result=prediction(raw,np.zeros((3,2)),np.eye(2),sigma)
    expected=np.sum(raw**2/sigma**2+np.log(2*np.pi*sigma**2))
    assert abs(result['negative_twice_log_density']-expected)<1e-12
