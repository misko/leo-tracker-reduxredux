import importlib.util
from pathlib import Path

import numpy as np
import pytest

MODULE = (
    Path(__file__).parents[2]
    / "reports/2026_09_23_position_drift_identifiability/helper/drift_information.py"
)
SPEC = importlib.util.spec_from_file_location("drift_information", MODULE)
drift = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(drift)


def test_shared_slope_projection_removes_only_slope_aligned_position_column():
    # Two tracks, with the east derivative exactly a shared time slope.
    track = np.array([0, 0, 0, 1, 1, 1])
    time = np.array([1.0, 2.0, 3.0, 10.0, 11.0, 12.0])
    local_time = np.array([-1.0, 0.0, 1.0, -1.0, 0.0, 1.0])
    derivative = np.column_stack([2 * local_time, np.array([1.0, -1.0, 0.0, 2.0, -2.0, 0.0])])
    before, after, _, _ = drift.profiled_information(derivative, track, time)
    assert before[0, 0] > 0
    assert after[0, 0] == pytest.approx(0.0, abs=1e-12)
    assert after[1, 1] > 0
