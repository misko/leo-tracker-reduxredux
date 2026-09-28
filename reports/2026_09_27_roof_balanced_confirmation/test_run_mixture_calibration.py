from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import mixture_reception_core as core
import mixture_calibration_inputs as adapter
import run_mixture_calibration as runner


def track():
    return core.TrackData(
        log_weights=np.log([.4, .6]),
        detection_design=np.ones((2, 2, 1)), matched=np.array([True, False]),
        ratio_design=np.ones((2, 2, 1)), log_ratio=np.array([.2, 0.]))


def test_component_summary_uses_joint_decomposition():
    layout = core.ParameterLayout(1, 1, np.array([False]), np.array([False]))
    theta = np.array([0., 0., 0.])
    actual = runner.component_summary(theta, (track(),), layout)
    assert actual["track_count"] == 1
    assert (actual["sums"]["detection_marginal_nll"]
            + actual["sums"]["conditional_ratio_increment_nll"]
            == pytest.approx(actual["sums"]["joint_nll"], abs=1e-12))


def test_shard_names_are_immutable_and_deterministic():
    sessions = [f"s{i}" for i in range(6)]
    assert runner.shard_path(0, sessions).name == "mixture-calibration-full.json"
    assert runner.shard_path(3, sessions).name == "mixture-calibration-fold-s2.json"


def test_fit_arm_uses_protocol_keywords_and_explicit_layout_comparison(monkeypatch):
    row = adapter.JoinedRow("s", "t", "o", "rx0", "1:lower", "1", 1.,
                            True, 0., np.array([0., .1, .2]))
    tracks = (adapter.JoinedTrack("s", "t", (1, 2, 3),
                                  np.log([.6, .3, .1]), (row,)),)
    schema = adapter.fit_schema(tracks)
    seen = {}
    def optimize(data, layout, **kwargs):
        seen.update(kwargs)
        return {"theta": np.zeros(layout.size).tolist(), "accepted": True}
    monkeypatch.setattr(runner.core, "optimize_multistart", optimize)
    actual = runner.fit_arm(tracks, tracks, schema, "mixture")
    assert actual["converged"] is True
    assert seen["gradient_tolerance"] == 1e-6
    assert seen["stability_tolerance"] == 1e-7
    assert seen["prediction_stability_tolerance"] == 1e-4


def test_aggregate_refuses_missing_shards(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HERE", tmp_path)
    fake_tracks = (SimpleNamespace(session_id="s", rows=()),)
    receipt = {"sessions": [f"s{i}" for i in range(6)], "source_hashes": {},
               "candidate_prior_sha256": {}, "rows": 6378, "tracks": 344}
    monkeypatch.setattr(runner.adapter, "load_joined", lambda: (fake_tracks, receipt))
    monkeypatch.setattr(runner.adapter, "structural_signature", lambda _: "sha256:x")
    monkeypatch.setattr(runner, "source_bindings", lambda _: {
        "code_and_protocol_sha256": {}, "input_source_hashes": {},
        "candidate_prior_sha256": {}, "structural_input_sha256": None})
    with pytest.raises(FileNotFoundError, match="missing immutable fit shard"):
        runner.aggregate()
