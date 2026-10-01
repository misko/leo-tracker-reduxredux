import numpy as np
import pytest
from centroid_ablation import aggregate


def test_mean_scatter_translation_rotation_and_variance_decomposition():
    points = np.array([[1.,2.],[-3.,1.],[2.,-4.],[4.,3.]])
    center, scatter = aggregate(points)
    rotation = np.array([[0.,-1.],[1.,0.]])
    translated, same_scatter = aggregate(points@rotation+np.array([20.,-9.]))
    np.testing.assert_allclose(translated, center@rotation+[20.,-9.])
    assert same_scatter == pytest.approx(scatter)
    target = np.array([3.,-2.])
    assert np.mean(np.sum((points-target)**2,axis=1)) == pytest.approx(scatter**2+np.sum((center-target)**2))


def test_single_identity_and_bad_inputs():
    center, scatter = aggregate([[2.,3.]])
    np.testing.assert_array_equal(center,[2.,3.])
    assert scatter == 0
    for value in ([], [[float('nan'),2]], [[1,2,3]], [1,2]):
        with pytest.raises(ValueError):
            aggregate(value)
