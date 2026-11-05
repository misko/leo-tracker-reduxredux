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
