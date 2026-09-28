import numpy as np
from ds9_quadrature_structure import agreement


def test_constant_agreement_is_also_constant_baseline():
    result = agreement(np.ones(100), np.ones(100))
    assert result["agreement"] == result["marginal_baseline"] == 1


def test_mask_limits_comparison_and_preserves_disagreement():
    result = agreement(np.array([1, 1, -1]), np.array([-1, 1, 1]), np.array([True, False, True]))
    assert result == dict(count=2, agreement=0.0, marginal_baseline=0.5)
