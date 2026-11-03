from types import SimpleNamespace

import numpy as np
import pytest

from tools.rx_held_frequency import extract_session, profile_candidates


def test_held_values_cannot_change_training_profile_or_weights() -> None:
    predicted = np.array([[0.0, 1.0, 2.0, 3.0], [2.0, 1.0, 0.0, -1.0]])
    measured = np.array([10.0, 11.0, 12.0, 13.0])
    mask = np.array([True, True, False, False])
    first = profile_candidates(measured, predicted, mask)
    changed = measured.copy()
    changed[~mask] += 1_000_000
    second = profile_candidates(changed, predicted, mask)
    for key in (
        "profiled_cfo_hz",
        "training_rms_hz",
        "training_log_likelihood",
        "candidate_probabilities",
    ):
        assert second[key] == pytest.approx(first[key])


def test_extract_emits_only_held_identity_and_likelihood() -> None:
    track = SimpleNamespace(
        track_id="track",
        observation_ids=("train", "held"),
        training_mask=np.array([True, False]),
        measured_hz=np.array([10.0, 12.0]),
        times_s=np.array([1e-9, 2e-9]),
    )
    associations = [
        {
            "track_id": "track",
            "projected_observation_id": oid,
            "observation_utc_ns": utc,
            "training": training,
            "candidate_ids": [7, 8],
            "candidate_probabilities": [0.5, 0.5],
            "candidate_training_rms_hz": [0.0, 0.0],
            "source_group_id": "group",
            "source_sample_start": 10,
            "source_sample_end": 20,
            "support_center_utc_ns": utc,
            "propagation_utc_ns": utc,
            "stream_id": "rx-0",
        }
        for oid, utc, training in (("train", 1, True), ("held", 2, False))
    ]

    rows, counts = extract_session(
        "session",
        associations,
        {("track", "held"): "source-hash"},
        [track],
        lambda _track, _ids: np.array([[0.0, 1.0], [2.0, 3.0]]),
        start_utc_ns=0,
    )
    assert counts["tracks"] == 1
    assert counts["held_rows"] == 1
    mask = counts["track_masks"][0]
    assert mask["track_id"] == "track"
    assert mask["candidate_ids"] == [7, 8]
    assert mask["candidate_probabilities"] == [0.5, 0.5]
    assert mask["candidate_training_rms_hz"] == [0.0, 0.0]
    assert mask["training_observation_ids"] == ["train"]
    assert mask["held_observation_ids"] == ["held"]
    assert [row["training"] for row in mask["observation_sources"]] == [True, False]
    assert mask["observation_sources"][0]["source_sample_start"] == 10
    assert rows[0]["observation_id"] == "held"
    assert rows[0]["source_candidate_id"] == "source-hash"
    assert rows[0]["candidate_residual_hz"] == pytest.approx([1.0, 1.0])
    assert len(rows[0]["candidate_log_likelihood"]) == 2


def test_extract_fails_if_frozen_training_summary_does_not_reproduce() -> None:
    track = SimpleNamespace(
        track_id="track",
        observation_ids=("train", "held"),
        training_mask=np.array([True, False]),
        measured_hz=np.array([10.0, 12.0]),
        times_s=np.array([0.0, 1e-9]),
    )
    associations = [
        {
            "track_id": "track",
            "projected_observation_id": oid,
            "observation_utc_ns": index,
            "training": training,
            "candidate_ids": [7],
            "candidate_probabilities": [1.0],
            "candidate_training_rms_hz": [1.0],
            "source_group_id": "group",
            "source_sample_start": 10,
            "source_sample_end": 20,
            "support_center_utc_ns": index,
            "propagation_utc_ns": index,
            "stream_id": "rx-0",
        }
        for index, (oid, training) in enumerate((("train", True), ("held", False)))
    ]
    with pytest.raises(ValueError, match="training RMS"):
        extract_session(
            "session",
            associations,
            {("track", "held"): "source-hash"},
            [track],
            lambda _track, _ids: np.zeros((1, 2)),
            start_utc_ns=0,
        )


def test_extract_rejects_timestamp_or_training_summary_drift() -> None:
    track = SimpleNamespace(
        track_id="track",
        observation_ids=("train", "held"),
        training_mask=np.array([True, False]),
        measured_hz=np.array([10.0, 12.0]),
        times_s=np.array([0.0, 1e-9]),
    )
    rows = [
        {
            "track_id": "track",
            "projected_observation_id": oid,
            "observation_utc_ns": utc,
            "training": training,
            "candidate_ids": [7],
            "candidate_probabilities": [probability],
            "candidate_training_rms_hz": [0.0],
            "support_center_utc_ns": utc,
            "propagation_utc_ns": utc,
        }
        for oid, utc, training, probability in (
            ("train", 0, True, 1.0),
            ("held", 2_000, False, 0.5),
        )
    ]
    with pytest.raises(ValueError, match="training summary"):
        extract_session(
            "session",
            rows,
            {("track", "held"): "source-hash"},
            [track],
            lambda _track, _ids: np.zeros((1, 2)),
            start_utc_ns=0,
        )
    rows[1]["candidate_probabilities"] = [1.0]
    with pytest.raises(ValueError, match="UTC mismatch"):
        extract_session(
            "session",
            rows,
            {("track", "held"): "source-hash"},
            [track],
            lambda _track, _ids: np.zeros((1, 2)),
            start_utc_ns=0,
        )
