"""Component-owned integrity and export checks for the frozen-corpus evaluator."""

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_polynomial_tracklets", ROOT / "tools/evaluate_polynomial_tracklets.py")
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


@dataclass
class Config:
    alias_spacing_hz: float = 1000.0


def test_frozen_loader_uses_all_observations_without_labels():
    rows, provenance = evaluator.load_observations(evaluator.DEFAULT_INPUT)
    assert len(rows) == 4797
    assert all(set(row) == set(evaluator.OBSERVATION_FIELDS) for row in rows)
    assert not any("associated" in key or "satellite" in key for row in rows for key in row)
    assert len(provenance["input_sha256"]) == 3


def test_frozen_loader_rejects_hash_change(tmp_path):
    for name in ("manifest.json", "sources.json", "context-observations.jsonl"):
        (tmp_path / name).write_bytes((evaluator.DEFAULT_INPUT / name).read_bytes())
    with (tmp_path / "context-observations.jsonl").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="does not match manifest"):
        evaluator.load_observations(tmp_path)


def test_export_reconstructs_alias_residual_and_preserves_unresolved(tmp_path):
    rows = [{"observation_id": f"id-{i}", "time_s": float(i), "receiver": 1,
             "channel": 1, "measured_cfo_hz": y}
            for i, y in enumerate([990.0, -5.0, 123.0])]

    def fitter(t, y, config):
        if len(t) == 0:
            return {"assignment": [], "alias_lifts": [], "tracks": []}
        return {"assignment": [0, 0, -1], "alias_lifts": [-1, 0, 0],
                "tracks": [{"indices": [0, 1], "pieces": [{"indices": [0, 1],
                    "degree": 1, "reference_time_s": 0.0, "time_scale_s": 1.0,
                    "coefficients_hz": [-10.0, 5.0], "start_s": 0.0, "end_s": 1.0}]}]}

    result, exports = evaluator.evaluate_lanes(rows, Config(), fitter)
    assert result["observations"] == 3
    assert result["assigned"] == 2
    assert result["unresolved"] == 1
    assert result["track_count"] == 1
    assert [x["residual_hz"] for x in exports] == [0.0, 0.0, None]
    assert [x["observation_id"] for x in exports] == [x["observation_id"] for x in rows]
    evaluator.save_results(tmp_path, result, exports)
    assert len((tmp_path / "assignments.csv").read_text().splitlines()) == 4
    assert json.loads((tmp_path / "results.json").read_text())["assigned"] == 2


def test_conditional_block_prediction_scores_every_selected_point():
    t = np.arange(40.0)
    piece = {"degree": 1, "reference_time_s": 20.0, "time_scale_s": 20.0}
    diagnostic = evaluator.conditional_block_prediction(t, 20 + 3 * t, piece)
    assert diagnostic["count"] == 40
    assert diagnostic["rms_hz"] < 1e-10
    assert "conditional" in diagnostic["status"]


def test_residual_diagnostics_exposes_structured_runs():
    r = np.r_[np.full(20, -10), np.full(20, 10)]
    diagnostic = evaluator.residual_diagnostics(np.arange(40), r)
    assert diagnostic["mean_hz"] == 0
    assert diagnostic["sign_runs"] == 2
    assert diagnostic["lag1_correlation_observation_order"] > 0.9
    assert diagnostic["normalized_cusum_max"] > 3
