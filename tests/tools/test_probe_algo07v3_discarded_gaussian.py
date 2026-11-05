import numpy as np
import pytest
from probe_algo07v3_assembly import exact_result
from probe_algo07v3_discarded_gaussian import candidate_function

from leo.analysis.localization_v3.discovery_likelihood import DiscoveryPosition
from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared


@pytest.mark.parametrize("fitted_c", [False, True])
@pytest.mark.parametrize("cls", [NormalPosition, DiscoveryPosition])
@pytest.mark.parametrize("point", [(0.0, 0.0), (1.0, -2.0), (-12.5, 12.5)])
def test_geometry_only_parent_preserves_all_position_fields(fitted_c, cls, point):
    scan, node = prepared()
    if cls is NormalPosition:
        problem = cls(scan, node, 150.0, fitted_c)
    else:
        problem = cls(scan, node["seed"], fitted_c, aliases=node["aliases"])
    original, candidate, _, _ = candidate_function(cls)
    x = np.array(point)
    exact_result(original(problem, x), candidate(problem, x))
    assert np.array_equal(x, point)
