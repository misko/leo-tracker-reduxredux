import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_08_position_error_iter04"))
from test_joint_clock import setup  # noqa: E402
from profile_fit import fit  # noqa: E402


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_fixed_position_keeps_location_and_audits_only_free_parameters(arm):
    _, model = setup()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    row = fit(model, seed, arm=arm, fixed_position=True, clock_seed=model.initial_clock)
    np.testing.assert_array_equal(row["vector"][:2], seed[:2])
    assert row["physical_constraints_minimum"] >= -1e-7
    assert row["converged"] == (row["stationarity"] <= 0.001)
    if arm == "zero-c":
        assert row["vector"][6] == 0


def test_rejects_invalid_warm_clock_seed():
    _, model = setup()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    with pytest.raises(ValueError, match="invalid clock seed"):
        fit(model, seed, arm="fitted-c", clock_seed=[float("nan")])
