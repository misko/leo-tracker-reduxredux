import copy
import json

import numpy as np
import pytest

from tools.rx_causal_geometry_cv import run, training_reception_document
from tools.rx_geometry_temporal_transfer import score_lanes


def _lane(session, split="calibration"):
    def window(role, index, observed):
        return {
            "role": role,
            "prediction_utc_ns": index * 1_000_000_000,
            "sample_rate_hz": 5_000_000,
            "source_window_id": f"{session}-{role}-{index}",
            "observed": {
                "rx0": [{"canonical_rx0_hz": value} for value in observed],
                "rx1": [],
            },
            "predictions": [],
        }

    return {
        "recording_split": split,
        "lane": {"session_id": session},
        "alias_period_hz": 227_000.0,
        "components": [{"kind": "other", "log_prior": None}],
        "windows": [window("reception", 1, [1.0]), window("held_frequency", 2, [2.0])],
    }


def test_training_document_excludes_held_record_held_rows_and_evaluation_before_reading() -> None:
    document = {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [_lane("a"), _lane("b"), _lane("evaluation", "evaluation")],
    }
    changed = copy.deepcopy(document)
    changed["lanes"][0]["windows"][1]["predictions"] = None
    changed["lanes"][0]["windows"][1]["observed"] = None
    changed["lanes"][1]["windows"][0]["predictions"] = None
    changed["lanes"][1]["windows"][0]["observed"] = None
    changed["lanes"][2]["windows"][0]["predictions"] = None
    changed["lanes"][2]["windows"][0]["observed"] = None
    restricted = training_reception_document(changed, "b")
    assert len(restricted["lanes"]) == 1
    assert restricted["lanes"][0]["lane"]["session_id"] == "a"
    assert [window["role"] for window in restricted["lanes"][0]["windows"]] == ["reception"]


def test_checkpoint_provenance_mismatch_is_rejected(tmp_path, monkeypatch) -> None:
    import tools.rx_causal_geometry_cv as module

    sessions = [f"s{index}" for index in range(6)]
    lanes = []
    for session in sessions:
        for channel in (1, 2):
            lane = _lane(session)
            lane["lane"]["channel"] = channel
            lanes.append(lane)
    document = {"schema": "rx-geometry-dataset/v1", "lanes": lanes}
    background = {
        "schema": "rx-empirical-background/v1",
        "mode": "joint",
        "rows": 5,
        "pooled_means": [1.0, 1.0],
        "pooled_counts": {"rows": 5, "histogram": [[1, 0, 5]], "tail_weight": 32.0},
    }
    fold = {
        "held_session": "s0",
        "training_sessions": sessions[1:],
        "training_window_count": 5,
        "background_model": background,
        "background_model_sha256": module._json_hash(background),
    }
    cv = {
        "schema": "rx-within-geometry-cv/v1",
        "status": "complete",
        "sigma_hz": 500.0,
        "folds": [
            {**fold, "held_session": s, "training_sessions": sorted(set(sessions) - {s})}
            for s in sessions
        ],
    }
    frozen = {
        "schema": "rx-causal-geometry/v1",
        "status": "complete",
        "folds": [{"held_session": s} for s in sessions],
    }
    (tmp_path / "fold-0.json").write_text(
        json.dumps(
            {
                "schema": "rx-causal-geometry-cv-fold/v1",
                "held_session": "wrong",
                "training_sessions": sessions[1:],
                "fingerprint": {},
                "fold": {},
            }
        )
    )
    monkeypatch.setattr(module, "_source_hashes", lambda: {})
    with pytest.raises(ValueError, match="checkpoint provenance"):
        run(
            document,
            cv,
            frozen,
            checkpoint_dir=tmp_path,
            experiment_seal="seal",
            input_hashes={"dataset": "a", "cv_results": "b", "frozen_results": "c"},
        )


def test_missing_experiment_seal_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="experiment_seal"):
        run({}, {}, {}, checkpoint_dir=tmp_path, experiment_seal="", input_hashes={})


def test_held_outcome_cannot_change_reception_prefix_score(monkeypatch) -> None:
    import tools.rx_geometry_temporal_transfer as transfer

    current = np.log([[1.0, 1.0], [0.4, 0.6], [0.8, 0.2]])
    monkeypatch.setattr(transfer, "relative_emissions", lambda lane, beta: current)
    lane = {
        "prior": np.array([0.0]),
        "times": np.array([0.0, 1.0, 4.0]),
        "roles": np.array(["reception", "reception", "held_frequency"]),
        "indices": [0, 1, 2],
        "reference": np.zeros(3),
        "source": {
            "lane": {"session_id": "s"},
            "windows": [
                {"source_window_id": str(index), "prediction_utc_ns": index * 1_000_000_000}
                for index in range(3)
            ],
        },
    }
    fitted = {"beta": [0.0], "occupancy": 0.5, "tau_s": 1.0}
    first = score_lanes([lane], fitted)
    current = current.copy()
    current[2] = np.log([0.001, 100.0])
    second = score_lanes([lane], fitted)
    assert second["roles"]["reception"] == first["roles"]["reception"]
