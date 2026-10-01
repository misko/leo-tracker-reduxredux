import numpy as np
import pytest
from conditional_track_evidence import nested_transform, conditional_student


def contrasts(n):
    return np.column_stack((-np.ones(n-1), np.eye(n-1)))


def test_conditional_density_matches_joint_marginal_ratio():
    rng = np.random.default_rng(8016)
    for n, p in ((7, 3), (15, 7)):
        raw = rng.normal(size=(n, n))
        covariance = raw@raw.T+np.eye(n)
        result = conditional_student(rng.normal(size=n), covariance, p)
        assert abs(result['log_density']-result['log_ratio']) < 1e-11
        assert result['degrees'] == 4+p


def test_nested_transform_preserves_base_marginal_and_density_change_of_basis():
    from conditional_track_evidence import log_student
    base, dense = ('a', 'c', 'e'), tuple('abcde')
    small, large = contrasts(3), contrasts(5)
    transform, added = nested_transform(base, dense, small, large)
    raw = np.diag([1., 2., 3., 4., 5.])+.2*np.ones((5, 5))
    covariance = large@raw@large.T
    joined = transform@covariance@transform.T
    assert added.tolist() == [1, 3]
    assert np.allclose(joined[:2, :2], small@raw[np.ix_([0,2,4], [0,2,4])]@small.T)
    residual = large@np.array([1., 3., 2., -1., 4.])
    assert abs(log_student(transform@residual, joined, 4)
               -log_student(residual, covariance, 4)+np.linalg.slogdet(transform)[1]) < 1e-11


def test_non_nested_or_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        nested_transform(('a', 'z'), tuple('abc'), contrasts(2), contrasts(3))
    with pytest.raises(ValueError):
        nested_transform(('a', 'a'), tuple('abc'), contrasts(2), contrasts(3))
