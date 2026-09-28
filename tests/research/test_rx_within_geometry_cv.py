import copy
import json

import numpy as np

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_geometry_fit import raw_features
from tools.rx_within_geometry_cv import (
    CHECKPOINT_SCHEMA,
    fold_scaler,
    prepare_reception_lanes,
    reception_document,
    run,
    within_center,
)


def _lane(session, split="calibration", held_east=0.9):
    def window(role, index, east, observed):
        return {
            "role": role,
            "prediction_utc_ns": index * 1_000_000_000,
            "sample_rate_hz": 5_000_000,
            "source_window_id": f"{session}-{role}-{index}",
            "observed": {
                "rx0": [{"canonical_rx0_hz": value} for value in observed],
                "rx1": [],
            },
            "predictions": [
                {
                    "los_enu_unit": {
                        "east": east,
                        "north": 0.0,
                        "up": np.sqrt(1 - east**2),
                    },
                    "mu_canonical_rx0_hz": 0.0,
                    "visible": True,
                }
            ],
        }

    return {
        "recording_split": split,
        "lane": {"session_id": session},
        "alias_period_hz": 227_000.0,
        "components": [
            {"kind": "track_candidate", "log_prior": 0.0},
            {"kind": "other", "log_prior": None},
        ],
        "windows": [
            window("reception", 1, 0.1, [1.0]),
            window("reception", 2, 0.2, [2.0]),
            window("held_frequency", 3, held_east, [3.0]),
        ],
    }


def _document():
    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            _lane("a"),
            _lane("b"),
            _lane("evaluation", split="evaluation"),
        ],
    }


def test_within_center_makes_geometry_means_zero_and_keeps_d_features() -> None:
    reception = reception_document(_document())
    lanes = prepare_reception_lanes(reception, np.zeros(8), np.ones(8))
    changed = within_center(lanes)
    for original, centered in zip(lanes, changed, strict=True):
        np.testing.assert_array_equal(centered["x"][..., :3], original["x"][..., :3])
        np.testing.assert_allclose(centered["x"][..., 3:8].mean(axis=0), 0.0, atol=1e-16)


def test_d_design_is_exactly_identical_after_within_centering() -> None:
    lanes = prepare_reception_lanes(_document(), np.zeros(8), np.ones(8))
    changed = within_center(lanes)
    for original, centered in zip(lanes, changed, strict=True):
        beta = np.array([-2.0, 0.3, -0.4])
        np.testing.assert_array_equal(centered["x"][..., :3] @ beta, original["x"][..., :3] @ beta)


def test_fold_scaler_excludes_held_record_and_all_nonreception_geometry() -> None:
    document = _document()
    first = fold_scaler(document, "b")
    changed = copy.deepcopy(document)
    changed["lanes"][1]["windows"][0]["predictions"][0]["los_enu_unit"] = None
    changed["lanes"][0]["windows"][2]["predictions"] = None
    changed["lanes"][2]["windows"][0]["predictions"] = None
    second = fold_scaler(changed, "b")
    np.testing.assert_array_equal(second[0], first[0])
    np.testing.assert_array_equal(second[1], first[1])


def test_reception_document_excludes_evaluation_calibration_held_and_outcomes() -> None:
    document = _document()
    extracted = reception_document(document)
    assert {lane["lane"]["session_id"] for lane in extracted["lanes"]} == {"a", "b"}
    assert all(
        window["role"] == "reception" for lane in extracted["lanes"] for window in lane["windows"]
    )
    raw_before = [raw_features(lane)[0] for lane in extracted["lanes"]]
    changed = copy.deepcopy(document)
    for lane in changed["lanes"]:
        for window in lane["windows"]:
            for receiver in ("rx0", "rx1"):
                window["observed"][receiver] = [{"canonical_rx0_hz": 99_999.0}]
    raw_after = [raw_features(lane)[0] for lane in reception_document(changed)["lanes"]]
    for first, second in zip(raw_before, raw_after, strict=True):
        np.testing.assert_array_equal(first, second)


def test_background_rows_ignore_evaluation_and_calibration_held_outcomes() -> None:
    document = _document()
    first = calibration_rows(document, expected_records=2)
    changed = copy.deepcopy(document)
    changed["lanes"][0]["windows"][2]["observed"]["rx0"] = [{"canonical_rx0_hz": 123_456.0}]
    for window in changed["lanes"][2]["windows"]:
        window["observed"]["rx0"] = [{"canonical_rx0_hz": 111_111.0}]
    assert calibration_rows(changed, expected_records=2) == first


def _six_record_document():
    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [_lane(f"record-{index}") for index in range(6)],
    }


def _mock_fit_result():
    return {
        "schema": "rx-joint-geometry-fit/v1",
        "fits": {
            arm: {
                "candidates": [],
                "selected": {
                    "beta": [0.0] * dimension,
                    "occupancy": 0.0,
                    "tau_s": 1.0,
                    "map_penalty": 0.0,
                    "map_gain": 0.0,
                    "calibration_relative_log_evidence": 0.0,
                    "null_selected": True,
                },
            }
            for arm, dimension in {"D": 3, "E": 4, "S": 6, "T": 8}.items()
        },
    }


def test_held_outcome_cannot_change_fold_training_inputs(monkeypatch) -> None:
    import tools.rx_within_geometry_cv as cv

    captured = []

    def fake_fit(lanes, old_fits):
        captured.append(
            [
                (
                    lane["source"]["lane"]["session_id"],
                    lane["counts"].tolist(),
                    lane["x"].tolist(),
                    lane["reference"].tolist(),
                )
                for lane in lanes
            ]
        )
        return _mock_fit_result()

    monkeypatch.setattr(cv, "fit_arms", fake_fit)
    monkeypatch.setattr(cv, "calibration_score", lambda lanes, beta, occupancy, tau: 0.0)
    document = _six_record_document()
    first = run(document, fold_index=0)
    first_inputs = copy.deepcopy(captured)
    captured.clear()
    changed = copy.deepcopy(document)
    changed["lanes"][0]["windows"][0]["observed"]["rx0"] = [{"canonical_rx0_hz": 99_999.0}]
    second = run(changed, fold_index=0)
    assert captured == first_inputs
    for key in ("feature_center", "feature_scale", "background_model_sha256"):
        assert second["folds"][0][key] == first["folds"][0][key]
    assert first["status"] == second["status"] == "incomplete"


def test_invalid_checkpoint_fold_membership_is_rejected(tmp_path) -> None:
    document = _six_record_document()
    digest = "dataset-digest"
    checkpoint = tmp_path / "fold-0.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema": CHECKPOINT_SCHEMA,
                "dataset_sha256": digest,
                "held_session": "wrong-session",
                "training_sessions": [],
                "fingerprint": {},
                "fold": {},
            }
        )
    )
    with np.testing.assert_raises_regex(ValueError, "checkpoint provenance"):
        run(
            document,
            fold_index=0,
            checkpoint_dir=tmp_path,
            dataset_sha256=digest,
            experiment_seal="expected-seal",
        )


def test_checkpoint_requires_experiment_seal(tmp_path) -> None:
    with np.testing.assert_raises_regex(ValueError, "experiment_seal"):
        run(_six_record_document(), fold_index=0, checkpoint_dir=tmp_path)
