import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = (
    Path(__file__).parents[2] / "reports/2026_09_23_long_cache_feasibility/helper/regular_cache.py"
)
SPEC = importlib.util.spec_from_file_location("regular_cache", PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_regular_cache_interpolates_and_rejects_outside_query():
    cache = {
        "receive_plus_tau_offset_ns": np.array([0, 10]),
        "position_ecef_km": np.array([[[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]]),
        "velocity_ecef_km_s": np.array([[[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]]]),
    }
    position, velocity = module.interpolate_states(cache, np.array([5]))
    assert position[0, 0, 0] == pytest.approx(5.0)
    assert velocity[0, 0, 0] == pytest.approx(2.0)
    with pytest.raises(ValueError, match="outside"):
        module.interpolate_states(cache, np.array([11]))
