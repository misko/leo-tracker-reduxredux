"""Numerical checks for common-support retrospective scanner comparisons."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "scan_glrt_rms", Path(__file__).parents[2] / "tools/evaluate_scan_glrt_rms.py"
)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def data():
    t = np.arange(40.0)
    y = 30000 - 3500 * t + 2 * t * t
    return dict(
        t=t,
        y=y,
        segment=np.array(["a"] * 40),
        margin=np.full(40, 0.1),
        control=np.full(40, 0.02),
        rank=np.zeros(40),
        integer=y.copy(),
    )


def test_exact_quadratic_predicts_later_observations():
    row = study.score_profile(data(), study.profiles()[0])
    assert row["common_heldout_rms_hz"] < 1e-7
    assert row["heldout_count"] == 16


def test_threshold_does_not_remove_difficult_holdout_points():
    a = data()
    a["y"][24:] += 1000
    a["margin"][24:] = 0.03
    profile = {"name": "margin_0.05", "gate": 0.05, "top_k": 8, "weight": "equal"}
    row = study.score_profile(a, profile)
    assert row["retention"] == 0.6
    assert row["common_heldout_rms_hz"] == pytest.approx(1000)
    assert row["retained_full_rms_hz"] < 1e-7


def test_weights_are_inverse_variance_not_squared_weights():
    t = np.arange(20.0)
    y = t + np.sin(t)
    s = np.array(["a"] * 20)
    mask = np.ones(20, bool)
    w = np.linspace(0.5, 2, 20)
    prediction = study.fit(t, y, s, mask, degree=1, weight=w)
    design = np.column_stack([np.ones(20), t])
    expected = design @ np.linalg.solve(design.T @ (w[:, None] * design), design.T @ (w * y))
    assert prediction == pytest.approx(expected)


def test_empty_training_segment_is_failure():
    a = data()
    a["margin"][:24] = 0.03
    profile = {"name": "margin_0.05", "gate": 0.05, "top_k": 8, "weight": "equal"}
    assert study.score_profile(a, profile)["status"] == "insufficient_support"


def test_bootstrap_clusters_replicated_receivers_within_scan():
    result = study.bootstrap_scan_ratio([("one", 50, 100)] * 20 + [("two", 100, 100)])
    assert result["scan_count"] == 2
    assert result["geometric_rms_ratio"] == pytest.approx(np.sqrt(0.5))


def test_integer_comparison_preserves_alias_errors():
    a = data()
    a["integer"][::3] += 227272.727
    row = study.score_profile(a, study.profiles()[-1])
    assert row["common_heldout_rms_hz"] > 10000


def test_blocked_predictions_retain_all_observations():
    a = data()
    retained = np.ones(40, bool)
    retained[15:18] = False
    a["y"][15:18] += 1000
    prediction = study.blocked_prediction(a["t"], a["y"], a["segment"], retained, degree=2)
    assert prediction.shape == (40,)
    assert a["y"][15:18] - prediction[15:18] == pytest.approx(np.full(3, 1000))


def test_alias_canonicalization_keeps_true_residuals():
    alias = 1 / 4.4e-6
    delta = np.array([20, alias + 20, -alias + 20, 70000])
    assert study.canonical_delta(delta, alias) == pytest.approx([20, 20, 20, 70000])
