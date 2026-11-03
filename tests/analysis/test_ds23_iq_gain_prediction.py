import numpy as np
from scipy.linalg import null_space

from ds23_iq_gain_prediction import target_gain_density


def test_target_gain_density_matches_dense_complex_covariance():
    rng = np.random.default_rng(917)
    basis = rng.normal(size=(23, 2))+1j*rng.normal(size=(23, 2))
    y = rng.normal(size=23)+1j*rng.normal(size=23)
    mean = np.array([.3+.4j, -.2+.5j])
    covariance = np.array([[.2, .04+.03j], [.04-.03j, .3]])
    q = null_space(np.ones((1, 23)))
    residual = q.conj().T@(y-basis@mean)
    dense = q.conj().T@(.5*np.eye(23)+basis@covariance@basis.conj().T)@q
    expected = np.vdot(residual, np.linalg.solve(dense, residual)).real+np.linalg.slogdet(dense)[1]+22*np.log(np.pi)
    np.testing.assert_allclose(target_gain_density(y, basis, mean, covariance, .5), expected, atol=1e-9)
