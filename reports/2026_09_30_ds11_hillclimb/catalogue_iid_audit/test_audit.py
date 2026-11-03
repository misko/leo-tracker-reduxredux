import importlib.util
from pathlib import Path

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("catalogue_iid_audit", HERE / "audit.py")
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


def test_offgrid_interpolation_matches_linear_state_rule():
    position = np.array([[[[0.0, 2.0, 4.0]], [[4.0, 6.0, 8.0]]]])
    velocity = np.array([[[[10.0, 20.0, 30.0]], [[14.0, 24.0, 34.0]]]])
    pos, vel, lo, hi, weight = audit.interpolate_states(
        position, velocity, np.array([0.0, 0.25]), 0.125
    )
    assert (lo, hi, weight) == (0, 1, 0.5)
    np.testing.assert_allclose(pos, [[[2.0, 4.0, 6.0]]])
    np.testing.assert_allclose(vel, [[[12.0, 22.0, 32.0]]])


def test_profile_mass_and_retained_leading_mapping():
    scores = np.array([-5.0, -1.0, -3.0, -2.0])
    visible = np.array([True, True, False, True])
    retained = np.array([True, True, True, False])
    result = audit.numerator_comparison(scores, visible, retained)
    expected = np.exp(np.logaddexp(-5.0, -1.0) - np.logaddexp(np.logaddexp(-5.0, -1.0), -2.0))
    assert result["retained_mass"] == pytest.approx(expected)
    assert result["best_index"] == 1
    assert result["best_retained"] is True


def test_profile_mass_detects_omitted_leading_candidate():
    result = audit.numerator_comparison(
        np.array([-4.0, -1.0]), np.array([True, True]), np.array([True, False])
    )
    assert result["best_index"] == 1
    assert result["best_retained"] is False
    assert result["retained_mass"] < 0.1


def test_actual_multiroot_profile_matches_full_minus_omitted_partition():
    import sys

    sys.path.insert(0, str(audit.ROOT / "tools"))
    import ds7_fast_baseline_adapter as fast

    residual = np.array(
        [
            [20.0, -10.0, 15.0, 5.0],
            [600.0, 620.0, 580.0, 610.0],
            [-200.0, 250.0, -220.0, 230.0],
        ]
    )
    mask = np.array([True, True, True, False])
    scores, _, audits, _ = fast.profile(residual, mask)
    assert all(row["converged"] for row in audits)
    result = audit.numerator_comparison(
        scores, np.ones(3, dtype=bool), np.array([True, False, True])
    )
    full = np.logaddexp.reduce(scores)
    kept = np.logaddexp(scores[0], scores[2])
    assert result["retained_mass"] == pytest.approx(np.exp(kept - full))


def test_replay_guard_rejects_nonfinite_or_large_discrepancy():
    audit.require_exact_replay(0.0, True)
    with pytest.raises(ValueError, match="replay failed"):
        audit.require_exact_replay(np.nan, True)
    with pytest.raises(ValueError, match="replay failed"):
        audit.require_exact_replay(1e-6, True)
    with pytest.raises(ValueError, match="replay failed"):
        audit.require_exact_replay(0.0, False)
