from dataclasses import asdict
import json
from types import SimpleNamespace

import numpy as np
import pytest

import mixture_reception_core as core
import run_mixture_polished_full as runner


def fixture():
    layout = core.ParameterLayout(1, 1, np.array([False]), np.array([False]))
    track = core.TrackData(
        log_weights=np.array([0.]), detection_design=np.ones((1, 2, 1)),
        matched=np.array([True, False]), ratio_design=np.ones((1, 2, 1)),
        log_ratio=np.array([.2, 0.]))
    theta = np.array([0., 0., 0.])
    objective, gradient = core.objective_gradient(theta, (track,), layout)
    runs = [{"theta": theta.tolist(), "objective": objective,
             "gradient_max_abs": float(np.max(np.abs(gradient)))} for _ in range(3)]
    return (track,), layout, runs


def test_original_objectives_must_reproduce_before_polish():
    tracks, layout, runs = fixture()
    checks = runner.verify_raw_objectives(runs, tracks, layout)
    assert len(checks) == 3 and max(row["absolute_difference"] for row in checks) == 0.
    runs[0]["objective"] += 1e-5
    with pytest.raises(ValueError, match="no longer reproduces"):
        runner.verify_raw_objectives(runs, tracks, layout)


def test_model_serialization_keeps_components_and_polish_diagnostics():
    tracks, layout, _runs = fixture()
    polished = {"theta": [0., 0., 0.], "accepted": True,
                "runs": [{"input_run": {"objective": 1.}}]}
    actual = runner.serialize_model(
        "M0", {"detection": ("intercept",), "ratio": ("intercept",)},
        layout, polished, tracks)
    assert actual["converged"] is True
    assert actual["polish"] is polished
    sums = actual["score_components"]["sums"]
    assert sums["detection_marginal_nll"] + sums[
        "conditional_ratio_increment_nll"] == pytest.approx(sums["joint_nll"])


def test_real_join_matches_every_frequency_reserve_denominator():
    tracks, _receipt = runner.adapter.load_joined()
    assert runner.verify_reserve_denominators(tracks) == {
        "tracks_checked": 344, "mismatches": 0,
        "reception_rows": 6378, "reserve_observations": 6378}


def test_schema_json_roundtrip_matches_real_frozen_artifact():
    tracks, receipt = runner.adapter.load_joined()
    raw = json.loads((runner.HERE / "mixture-calibration-full.json").read_text())
    schema, bindings = runner.verify_original_artifact(raw, tracks, receipt)
    assert raw["feature_schema"] == runner.json_value(asdict(schema))
    assert bindings == raw["bindings"]


def test_original_artifact_preflight_rejects_schema_drift():
    tracks, receipt = runner.adapter.load_joined()
    raw = json.loads((runner.HERE / "mixture-calibration-full.json").read_text())
    raw["feature_schema"]["detection_channel_edges"][0] = "changed"
    with pytest.raises(ValueError, match="feature schema"):
        runner.verify_original_artifact(raw, tracks, receipt)
