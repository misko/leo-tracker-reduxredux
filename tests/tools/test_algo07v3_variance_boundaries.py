"""Exactness at allocation-policy boundaries and with strided physical inputs."""

import numpy as np
import pytest
from algo07v3_prevariance_hierarchical_oracle import hierarchical_bound
from probe_algo07v3_assembly import exact_result
from probe_algo07v3_variance_groups import candidate_function


@pytest.mark.parametrize("group_count", [7, 8, 9])
@pytest.mark.parametrize("strided", [False, True])
def test_batch_threshold_preserves_output_and_inputs(group_count, strided):
    # 8 groups * 128**2 * 8 bytes is exactly the prototype's 1 MiB threshold.
    # Both sides of the gate must retain the reference arithmetic.
    rng = np.random.default_rng(6032)
    n, width = group_count * 5, 128
    storage = rng.normal(size=(n * 2, width * 2))
    features = storage[::2, ::2] if strided else storage[:n, :width].copy()
    features *= np.logspace(-3, 3, width)
    raw = rng.normal(size=n) * 200
    sigma = rng.uniform(30, 180, n)
    groups = (np.arange(n) % group_count) * 7 + 13
    arguments = (raw, features, sigma, groups)
    saved = [a.copy() for a in arguments]
    options = dict(prior_groups=np.arange(width) // 9 - 1, prior_nu=2.1,
                   noise_nu=1.0, powers=np.linspace(.1, 1, group_count), iterations=32)
    candidate, _, _ = candidate_function()
    exact_result(hierarchical_bound(*arguments, **options), candidate(*arguments, **options))
    for before, after in zip(saved, arguments, strict=True):
        assert before.tobytes() == after.tobytes()


@pytest.mark.parametrize("iterations", [1, 2, 17])
def test_mixed_singleton_and_repeated_group_widths(iterations):
    rng = np.random.default_rng(27)
    n, width = 60, 12
    groups = np.arange(n) % 6
    features = rng.normal(size=(n, width))
    for group, count in enumerate([0, 1, 1, 3, 7, 7]):
        features[np.ix_(groups == group, np.arange(width) >= count)] = 0
    raw = rng.normal(size=n)
    candidate, _, _ = candidate_function()
    exact_result(
        hierarchical_bound(raw, features, 3.0, groups, iterations=iterations),
        candidate(raw, features, 3.0, groups, iterations=iterations),
    )
