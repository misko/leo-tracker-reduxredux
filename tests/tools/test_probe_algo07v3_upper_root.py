import numpy as np
import pytest
from probe_algo07v3_assembly import exact_result
from probe_algo07v3_upper_root import candidate_function

from leo.analysis.localization_v3.hierarchical import hierarchical_bound


@pytest.mark.parametrize("width", [0, 1, 16, 190])
@pytest.mark.parametrize("layout", ["C", "F"])
def test_upper_root_retains_every_output_bit(width, layout):
    rng = np.random.default_rng(519)
    u = rng.normal(size=(97, width))
    u[rng.random(u.shape) < 0.5] = 0
    u = np.array(u, order=layout)
    raw, sigma, groups = rng.normal(size=97) * 100, rng.uniform(3, 40, 97), np.arange(97) % 5
    kwargs = dict(
        prior_groups=np.arange(width) // 5 - 1, powers=np.linspace(0.1, 1, 5), iterations=16
    )
    function, _, _ = candidate_function()
    exact_result(
        hierarchical_bound(raw, u, sigma, groups, **kwargs),
        function(raw, u, sigma, groups, **kwargs),
    )


@pytest.mark.parametrize("n,width", [(7, 24), (53, 8), (53, 64)])
@pytest.mark.parametrize("degenerate", [False, True])
def test_upper_root_full_budget_heterogeneous_and_rank_deficient(n, width, degenerate):
    """Exercise the solve at strong/weak scales and more modes than observations."""
    rng = np.random.default_rng(871)
    u = rng.normal(size=(n, width)) * np.logspace(-3, 3, width)
    if degenerate:
        u[:, 1::3] = u[:, :1]
        u[:, 2::3] = -0.0
    raw = rng.normal(size=n) * 1e4
    sigma = np.logspace(-1, 2, n)
    groups = np.arange(n) % 3 * 7
    kwargs = dict(
        prior_groups=np.arange(width) // 4 - 1,
        powers=np.array([0.01, 0.5, 1.0]),
        iterations=256,
    )
    original_inputs = [a.copy() for a in (raw, u, sigma, groups)]
    function, _, _ = candidate_function()
    exact_result(
        hierarchical_bound(raw, u, sigma, groups, **kwargs),
        function(raw, u, sigma, groups, **kwargs),
    )
    for before, after in zip(original_inputs, (raw, u, sigma, groups), strict=True):
        assert before.tobytes() == after.tobytes()
