import numpy as np
from tile_receipt_audit import geometry


def test_geometry_detects_inconsistent_pairwise_correlations():
    assert geometry(np.array([.9, .9, -.9]))["negative_eigenvalues"] == 1
    assert geometry(np.array([0., 0., 0.]))["minimum_gram_eigenvalue"] == 1
