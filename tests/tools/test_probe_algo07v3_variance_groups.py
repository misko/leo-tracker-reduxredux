import numpy as np
import pytest
from probe_algo07v3_assembly import exact_result
from probe_algo07v3_variance_groups import candidate_function

from leo.analysis.localization_v3.hierarchical import hierarchical_bound


@pytest.mark.parametrize("width", [0, 1, 16, 190])
@pytest.mark.parametrize("layout", ["C", "F"])
@pytest.mark.parametrize("pattern", ["dense", "sparse", "local"])
def test_equal_shape_reductions_retain_every_output_bit(width, layout, pattern):
    rng = np.random.default_rng(708)
    n, group_count = 301, 17
    groups = np.arange(n) % group_count
    features = rng.normal(size=(n, width))
    if pattern == "sparse":
        features[rng.random(features.shape) < 0.9] = 0
    if pattern == "local":
        # Repeated widths, zero-column groups and shared hardware-like columns.
        for k in range(group_count):
            columns = np.arange(width)
            keep = (columns < k % 3) | ((columns // 4) % 7 == k % 7)
            features[np.ix_(groups == k, ~keep)] = 0
    features = np.array(features, order=layout)
    raw, sigma = rng.normal(size=n) * 100, rng.uniform(3, 40, n)
    before = [a.copy() for a in (raw, features, sigma, groups)]
    kwargs = dict(prior_groups=np.arange(width) // 5 - 1,
                  powers=np.linspace(0.05, 1.0, group_count), iterations=64)
    candidate, _, _ = candidate_function()
    exact_result(hierarchical_bound(raw, features, sigma, groups, **kwargs),
                 candidate(raw, features, sigma, groups, **kwargs))
    for a, b in zip(before, (raw, features, sigma, groups), strict=True):
        assert a.tobytes() == b.tobytes()
