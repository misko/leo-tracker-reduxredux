from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).with_name("polish_joint.py")
SPEC = importlib.util.spec_from_file_location("polish_joint", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_budget_uses_only_remaining_cumulative_time_with_safety_margin() -> None:
    external, internal = MODULE._remaining_budget(
        {"wall_seconds": 83.47}, {"wall_seconds": 46.18},
    )
    np.testing.assert_allclose([external, internal], [50.35, 45.35])


def test_only_successful_terminal_unresolved_continuation_is_eligible() -> None:
    continuation = {"status": "unresolved", "best": {
        "converged": False, "objectives": [2.0, 1.0],
    }}
    launch = {"status": "complete", "returncode": 0}
    assert MODULE._eligible(continuation, launch)
    continuation["best"]["converged"] = True
    assert not MODULE._eligible(continuation, launch)
    continuation["best"]["converged"] = False
    launch["status"] = "timeout"
    assert not MODULE._eligible(continuation, launch)


def test_winner_keeps_global_minimum_across_old_and_polished_modes() -> None:
    modes = [
        {"objectives": [3.0], "name": "primary"},
        {"objectives": [2.0], "name": "continuation"},
        {"objectives": [2.5], "name": "polish"},
    ]
    assert MODULE._best(modes)["name"] == "continuation"


def test_original_flat_spatial_and_gaussian_nuisance_precision() -> None:
    np.testing.assert_array_equal(
        MODULE._prior_precision(9), np.array([0.0, 0.0, 1.0, 4.0, 4.0, 4.0, 4.0, 4.0]),
    )
