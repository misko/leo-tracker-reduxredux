import numpy as np
import pytest
from ds23_predictive_position_search import search


def test_predictive_descent_starts_cold_and_preserves_regional_bounds():
    points=[]
    def score(x):points.append(x.copy());return np.sum((x-[1.25,-2.5])**2)
    result=search(score)
    assert result['converged'];np.testing.assert_allclose(points[0],[0.,0.],atol=0)
    # Gradient tolerance .01 implies at most5m error for this Hessian2I.
    assert np.linalg.norm(result['position']-[1.25,-2.5])<.00501
    assert result['maximum_gradient']<=.01
    edge=search(lambda x:np.sum((x-[20.,-30.])**2))
    np.testing.assert_allclose(edge['position'],[12.5,-12.5],atol=1e-6)


def test_predictive_descent_rejects_nonfinite_scores():
    with pytest.raises(ValueError,match='not finite'):search(lambda x:np.nan)
