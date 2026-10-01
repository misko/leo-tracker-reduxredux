import numpy as np
from group_influence import deletion, profile


def test_deletion_matches_exact_quadratic_refit():
    rng = np.random.default_rng(410)
    A = rng.normal(size=(12, 4)); y = rng.normal(size=12)
    prior = np.eye(4)*.2
    H = A.T@A+prior; x = np.linalg.solve(H, A.T@y)
    residual = A@x-y; g = A.T@residual+prior@x
    B = A[:3]; Hg = B.T@B; gg = B.T@residual[:3]
    answer = deletion(H, g, Hg, gg)
    exact = np.linalg.solve(A[3:].T@A[3:]+prior, A[3:].T@y[3:])
    assert answer['valid'] and 0 <= answer['maximum_leverage'] < 1
    np.testing.assert_allclose(x+answer['delta'], exact, atol=1e-12)


def test_profile_matches_full_inverse_position_block():
    rng = np.random.default_rng(8); A = rng.normal(size=(8, 5))
    H = A.T@A+np.eye(5)
    np.testing.assert_allclose(np.linalg.inv(profile(H)), np.linalg.inv(H)[:2, :2], atol=1e-12)


def test_singular_deletion_is_explicit_failure():
    result = deletion(np.eye(3), np.zeros(3), np.eye(3), np.zeros(3))
    assert not result['valid']
