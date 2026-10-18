"""Numerical derivatives and fresh-state rules without archived radio inputs."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from map_dsx01_clean_region import SPECS, finite_gradient  # noqa: E402
from run_dsx01_clean_region import reference_state  # noqa: E402


def test_gradient_matches_an_independent_quadratic_derivative():
    matrix = np.array([[4.0, 1.0], [1.0, 3.0]])
    optimum = np.array([2.0, -3.0])

    def objective(x):
        d = np.asarray(x) - optimum
        return d @ matrix @ d + 17

    point = np.array([-1.0, 4.0])
    np.testing.assert_allclose(
        finite_gradient(objective, point), 2 * matrix @ (point - optimum), atol=1e-9
    )


def test_numerical_phase_reference_is_bounded_without_mutating_source_state():
    original = dict(beta=[0] * 8, phases=[-20, 0, 50], extra={}, smooth=[[0], [0]])
    clipped = reference_state(original)
    np.testing.assert_array_equal(clipped["phases"], [-15, 0, 15])
    assert original["phases"] == [-20, 0, 50]


def test_current_comparison_inventory_includes_all_prior_causal_and_frame_variants():
    assert len(SPECS) == 38
    assert {"normal", "weak_3", "native_rx", "full_history", "frame_pooled_300"} <= SPECS.keys()


def test_linears_cannot_create_their_own_calibration_owners(monkeypatch):
    import map_dsx01_clean_linear as linear

    curved = dict(key="curve", receiver=1, channel=1, times=np.arange(6.0), values=np.zeros(6))
    straight = dict(key="line", receiver=2, channel=1, times=np.arange(6.0), values=np.zeros(6))
    scan = SimpleNamespace(tracks=[curved, straight], curved=[0])
    p = SimpleNamespace(scan=scan, members=[0], supported=[7])
    metrics = dict(tracks=[dict(candidate_index=7, compatible=True)])
    monkeypatch.setattr(
        linear, "curve_posterior", lambda *args: ({"coefficient": np.zeros(0)}, np.zeros((0, 0)))
    )
    monkeypatch.setattr(linear, "background_logprob", lambda *args: {"log_probability": 0.0})

    def forbidden(*args):
        raise AssertionError("one curved owner must not nominate a linear calibration family")

    monkeypatch.setattr(linear, "transfer_design", forbidden)
    rows = linear.nominations_for(p, np.zeros(2), metrics)
    assert len(rows) == 1 and rows[0]["component"] == "line"
    assert not rows[0]["accepted"] and "candidate_index" not in rows[0]
