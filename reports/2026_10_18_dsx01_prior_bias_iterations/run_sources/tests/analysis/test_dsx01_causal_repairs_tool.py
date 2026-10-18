"""Causal forecast and band-specific radio curvature numerical controls."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_causal_repairs")
    finally:
        sys.path.remove(path)


def test_band_curvature_zero_parity_and_receiver_band_separation(tool):
    scan, seed = problem_inputs()
    for t in scan.tracks:
        if t["channel"] == 4:
            t["channel"] = 6
    p = tool.BandCurvatureFamilies(scan, seed, "shared_phase", False, (0, 0))
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    np.testing.assert_allclose(p.residual(p.initial)[8:], base.residual(base.initial))
    x = p.initial.copy()
    k = p.radio_keys.index(("contrast", 0, 0))
    x[p.base_size + k] = 0.7
    df = p.predicted(x)[0] - p.predicted(p.initial)[0]
    for t, block in zip(scan.tracks, p.slices, strict=True):
        if t["receiver"] == 2:
            np.testing.assert_allclose(df[block], 0, atol=1e-9)
        else:
            sign = 1 if t["channel"] > 4 else -1
            np.testing.assert_allclose(
                df[block], sign * 70 * tool.temporal_curvature(t["times"])[:, 0], atol=1e-8
            )


def test_band_curvature_priors_do_not_replace_radio_or_phase_priors(tool):
    scan, seed = problem_inputs()
    p = tool.repair_problem(scan, seed, "shared_phase", True, (0, 0), variant="band_curvature")
    x = p.initial.copy()
    x[-1], x[p.pairs[0][0]], x[p.pairs[1][1]] = 0.6, 0.8, 0.2
    r = p.residual(x)
    np.testing.assert_allclose(r[:8], x[-8:])
    start = len(r) - len(p.labels) - 4
    np.testing.assert_allclose(r[start : start + 4], [0.8, 0, 0, 0.2])
    assert p.decode(x)["radio_curvature_hz"][-1] == pytest.approx(60)
    np.testing.assert_allclose(p.decode(x)["beta"][6:8] / 150, [-0.1, 0.1])


def test_causal_forecast_rejects_future_epochs_collections_and_fields(tool):
    forecast = importlib.import_module("build_dsx01_causal_forecast")
    data = dict(
        cutoff_utc_ns=100,
        candidates={
            "1": dict(
                latest_causal=dict(epoch=90), past_versions=[dict(epoch=80, collected_utc_ns=95)]
            )
        },
    )
    forecast.validate_history(data)
    row = data["candidates"]["1"]
    row["past_versions"][0]["collected_utc_ns"] = 101
    with pytest.raises(ValueError, match="noncausal"):
        forecast.validate_history(data)
    row["past_versions"][0]["collected_utc_ns"] = 95
    row["latest_causal"]["epoch"] = 101
    with pytest.raises(ValueError, match="future"):
        forecast.validate_history(data)
    row["latest_causal"]["epoch"] = 90
    row["first_following_newer_version"] = None
    with pytest.raises(ValueError, match="past-only"):
        forecast.validate_history(data)


def test_forecast_shrinkage_recovers_predictable_innovation_and_bounds(tool):
    forecast = importlib.import_module("build_dsx01_causal_forecast")
    rng = np.random.default_rng(16)
    pairs = []
    for _ in range(60):
        x = rng.normal(0, 0.3, 18)
        pairs.append(dict(predictor=x, target=0.6 * x))
    assert forecast.fit_shrinkage(pairs) == pytest.approx(0.6, abs=0.02)
    assert forecast.fit_shrinkage([]) == 0
    assert forecast.fit_shrinkage([dict(predictor=np.ones(18), target=10 * np.ones(18))]) <= 1


def test_phase_aligned_causal_innovation_zero_identity(tool):
    forecast = importlib.import_module("build_dsx01_causal_forecast")
    record = dict(
        lines=[
            "1 69333U 26181B   26289.21674716  .00020749  00000-0  76268-3 0  9998",
            "2 69333  53.1598 129.9450 0001425  79.1131 281.0026 15.25668438  5934",
        ]
    )
    p, v, phase = forecast.innovation(record, record, 1792189937829405937, np.arange(-20, 321.0))
    np.testing.assert_allclose(p, 0, atol=1e-10)
    np.testing.assert_allclose(v, 0, atol=1e-12)
    assert phase == pytest.approx(0)
