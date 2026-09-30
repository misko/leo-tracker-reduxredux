import numpy as np
import pytest
from ds9_carrier_scope import contributions


def test_carrier_covariance_partition_preserves_sign_and_rejects_missing_support():
    rng = np.random.default_rng(80)
    bins = np.r_[516:528, 536:548]
    a = rng.normal(size=(23, 6, 24))
    b = a.copy()
    b[..., 12:] *= -0.25
    rows = contributions(a, b, bins)
    assert rows[0]["covariance_fraction"] > 1
    assert rows[1]["covariance_fraction"] < 0
    assert abs(sum(r["covariance_fraction"] for r in rows) - 1) < 1e-12
    np.testing.assert_allclose([r["correlation"] for r in rows], [1, -1])
    with pytest.raises(ValueError, match="complete"):
        contributions(a[..., 1:], b[..., 1:], bins[1:])
