import numpy as np
from metadata_receipt_audit import adjusted


def test_bh_restores_feature_order_and_monotonicity():
    np.testing.assert_allclose(adjusted([.8, .01, .04]), [.8, .03, .06])
