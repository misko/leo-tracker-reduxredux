import numpy as np
from early_tree_audit import evaluate
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import pdist


def test_saved_tree_must_match_features_and_reordering_keeps_labels_aligned():
    x = np.random.default_rng(19).normal(size=(16, 5))
    result = evaluate(x, linkage(pdist(x), method="average"), repeats=3)
    np.testing.assert_allclose(result["minimum_ARI"], [1, 1, 1])
