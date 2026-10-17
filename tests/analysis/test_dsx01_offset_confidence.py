"""Scientific checks for curvature evidence used in the confidence audit."""

import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def audit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("audit_dsx01_offset_confidence")


def test_noise_and_weak_quadratic_are_not_active_curvature(audit):
    t = np.linspace(0, 40, 80)
    rng = np.random.default_rng(91)
    for y in (10000 + 200 * t + rng.normal(0, 150, len(t)), 10000 + 200 * t + 0.03 * (t - 20) ** 2):
        result, _ = audit.curvature(t, y)
        assert not result["active"]


def test_active_curvature_is_invariant_to_offsets_drifts_and_alias_lifts(audit):
    t = np.linspace(0, 60, 100)
    y = 2 * (t - 30) ** 2 + np.random.default_rng(3).normal(0, 100, len(t))
    a, _ = audit.curvature(t, y)
    b, _ = audit.curvature(t, y + 2 * audit.ratio({"rf_hz": 11.5e9}, True) * 227272.727 + 400 * t)
    assert a["active"] and b["active"]
    assert a["nonlinear_rms_hz"] == pytest.approx(b["nonlinear_rms_hz"])


def test_curvature_must_be_supported_inside_actual_overlap(audit):
    def track(key, times):
        return {
            "key": key,
            "start_s": float(times.min()),
            "end_s": float(times.max()),
            "times": times,
            "values": 2 * (times - 30) ** 2,
            "rf_hz": 11.5e9,
        }

    a = track("a", np.linspace(0, 60, 121))
    b = track("b", np.linspace(58, 100, 85))
    e = audit.pair_evidence({"left_key": "a", "right_key": "b"}, {"a": a, "b": b})
    assert not e["both_active"]
    assert e["left_n"] == 5


def test_different_curvatures_do_not_pass_shape_compatibility(audit):
    t = np.linspace(0, 60, 101)
    tracks = {
        k: {
            "key": k,
            "start_s": 0,
            "end_s": 60,
            "times": t,
            "values": scale * (t - 30) ** 2,
            "rf_hz": 11.5e9,
        }
        for k, scale in (("a", 2), ("b", -2))
    }
    e = audit.pair_evidence({"left_key": "a", "right_key": "b"}, tracks)
    assert e["both_active"]
    assert not e["curvature_compatible"]


def test_known_rf_scaling_matches_curvature_before_hardware_calibration(audit):
    t = np.linspace(0, 60, 101)
    tracks = {
        k: {
            "key": k,
            "start_s": 0,
            "end_s": 60,
            "times": t,
            "values": q * 2 * (t - 30) ** 2 + 45000 * i + 7 * i * t,
            "rf_hz": q * 11.5e9,
        }
        for i, (k, q) in enumerate((("a", 0.94), ("b", 1.08)))
    }
    e = audit.pair_evidence({"left_key": "a", "right_key": "b"}, tracks)
    assert e["curvature_compatible"]
    assert e["curvature_mismatch_hz"] < 1e-7


def test_linear_tracks_have_zero_influence_on_curvature_calibration(audit):
    t = np.linspace(0, 60, 101)
    mapping = {}
    for key, rx, curved in (("a", 1, True), ("b", 2, True), ("c", 1, False), ("d", 2, False)):
        mapping[key] = {
            "key": key,
            "receiver": rx,
            "bank": "CH1-4",
            "rf_hz": 11.5e9,
            "start_s": 0,
            "end_s": 60,
            "times": t,
            "values": (2 * (t - 30) ** 2 if curved else 800 * t)
            + (rx - 1) * (10000 + 3 * (t - 150) if curved else 80000 - 12 * t),
        }
    pairs = [
        {"left_key": a, "right_key": b, "left_lift": 0, "right_lift": 0, "start_s": 0, "end_s": 60}
        for a, b in (("a", "b"), ("c", "d"))
    ]
    curved = audit.curved_data_fit(pairs[:1], mapping)
    combined = audit.curved_data_fit(pairs, mapping)
    np.testing.assert_allclose(curved["beta"], combined["beta"])
    beta = np.asarray(combined["beta"])
    assert beta[2] - beta[0] == pytest.approx(10000)
    assert (beta[6] - beta[4]) / 150 == pytest.approx(3)
    assert combined["observations"] == 202
    assert audit.curved_data_fit(pairs[1:], mapping) is None


def test_linear_overlap_remains_eligible_with_fixed_calibration(audit):
    prototype = importlib.import_module("prototype_multilane_tracklets")
    t = np.linspace(0, 40, 81)
    mapping = {}
    beta = np.array([0.0, 0.0, 10000.0, 0.0, 0.0, 0.0, 450.0, 0.0])
    rng = np.random.default_rng(8)
    for rx in (1, 2):
        key = f"r{rx}"
        values = 1000 * t + (rx - 1) * (10000 + 3 * (t - 150))
        values += rng.normal(0, 50, len(t))
        coeff = np.polynomial.legendre.legfit((t - 20) / 20, values, 1)
        mapping[key] = {
            "key": key,
            "source_id": "test",
            "receiver": rx,
            "channel": 1,
            "bank": "CH1-4",
            "rf_hz": 11.5e9,
            "start_s": 0,
            "end_s": 40,
            "times": t,
            "values": values,
            "observation_ids": [f"{key}-{i}" for i in range(len(t))],
            "pieces": [
                {
                    "degree": 1,
                    "coefficients_hz": coeff,
                    "reference_time_s": 20,
                    "time_scale_s": 20,
                    "start_s": 0,
                    "end_s": 40,
                }
            ],
        }
    assert not audit.pair_evidence({"left_key": "r1", "right_key": "r2"}, mapping)["both_active"]
    fit, reason = prototype.fit_union({"r1": 0, "r2": 0}, mapping, beta, True)
    assert reason == "accepted"
    assert fit["degree"] == 1 and fit["points"] == 162
