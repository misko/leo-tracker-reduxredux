import copy
import hashlib
import json
import sys

import pytest

from tools.rx_track_competition import analyze, main


def _lane(session="s0", reception=(True,), held=(False,)):
    components = [
        {"kind": "track_candidate", "track_id": "t0", "catalog_number": 1, "log_prior": 0.0},
        {"kind": "track_candidate", "track_id": "t0", "catalog_number": 2, "log_prior": 0.0},
        {"kind": "track_candidate", "track_id": "t1", "catalog_number": 3, "log_prior": -100.0},
        {"kind": "track_candidate", "track_id": "t1", "catalog_number": 4, "log_prior": None},
        {"kind": "other", "log_prior": None},
    ]
    windows = []
    specifications = [("reception", value) for value in reception] + [
        ("held_frequency", value) for value in held
    ]
    for index, (role, observed) in enumerate(specifications):
        candidates = (
            [{"candidate_id": f"{session}-{index}-c", "canonical_rx0_hz": 5.0}]
            if observed
            else []
        )
        windows.append(
            {
                "source_window_id": f"{session}-w{index}",
                "role": role,
                "prediction_utc_ns": 10_000_000_000 + index * 1_000_000_000,
                "observed": {"rx0": candidates, "rx1": copy.deepcopy(candidates)},
                "predictions": [
                    {
                        "track_id": "t0",
                        "catalog_number": 1,
                        "visible": True,
                        "mu_canonical_rx0_hz": 5.0,
                    },
                    {
                        "track_id": "t0",
                        "catalog_number": 2,
                        "visible": True,
                        "mu_canonical_rx0_hz": 3_000.0,
                    },
                    {
                        "track_id": "t1",
                        "catalog_number": 3,
                        "visible": False,
                        "mu_canonical_rx0_hz": 5.0,
                    },
                    {
                        "track_id": "t1",
                        "catalog_number": 4,
                        "visible": True,
                        "mu_canonical_rx0_hz": 5.0,
                    },
                ],
            }
        )
    return {
        "recording_split": "evaluation",
        "lane": {
            "session_id": session,
            "channel": 3,
            "edge": "upper",
            "actual_rf_hz": 11_440_000_000.0,
        },
        "alias_period_hz": 10_000.0,
        "components": components,
        "windows": windows,
    }


def _mapping(sessions=("s0",)):
    tracks = []
    for session in sessions:
        for track_id, candidate_id in (("t0", "prefix-a"), ("t1", "prefix-b")):
            tracks.append(
                {
                    "session_id": session,
                    "track_id": track_id,
                    "receiver_id": 0,
                    "channel": 3,
                    "edge": "upper",
                    "actual_rf_hz": 11_440_000_000.0,
                    "training_alias_points": [
                        {
                            "source_window_id": f"{session}-prefix-window",
                            "candidate_id": f"{session}-{candidate_id}",
                            "observation_id": f"{session}-{candidate_id}-observation",
                            "support_center_utc_ns": 1_000_000_000,
                        }
                    ],
                }
            )
    return {"schema": "rx-training-alias-mapping/v1", "status": "complete", "tracks": tracks}


def test_track_conditional_weights_ceiling_empty_windows_and_overlap_evidence():
    result = analyze({"schema": "rx-geometry-dataset/v1", "lanes": [_lane()]}, _mapping())
    lane = result["lanes"][0]
    first = lane["windows"][0]
    assert first["metrics"]["frozen_prior_weighted_rx0_within_500hz"] == pytest.approx(0.5)
    assert first["metrics"]["optimistic_track_conditional_max_rx0_within_500hz"] == pytest.approx(
        0.5
    )
    assert first["metrics"]["any_nominee_ceiling_rx0_within_500hz"] == 1.0
    assert first["tracks"]["t0"]["forecast_age_s"] == 9.0
    empty = lane["windows"][1]
    assert all(value == 0 for value in empty["metrics"].values())
    overlap = lane["prefix_track_pair_overlaps"][0]
    assert overlap["shared_source_windows"] == 1
    assert overlap["distinct_observation_overlap_windows"] == 1
    assert overlap["windows"][0]["candidate_id_sets_disjoint"] is True
    assert overlap["windows"][0]["observation_id_sets_disjoint"] is True
    assert lane["tracks"][0]["conditional_nominees"][0]["track_id"] == "t0"


def test_role_aggregate_uses_equal_record_weight_not_pooled_windows():
    document = {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [_lane("s0", reception=(True, True, True), held=()), _lane("s1", (False,), ())],
    }
    result = analyze(document, _mapping(("s0", "s1")))
    aggregate = result["aggregate_equal_record"]["reception"]
    assert aggregate["windows"] == 4
    assert aggregate["metrics"]["any_nominee_ceiling_rx0_within_500hz"] == pytest.approx(0.5)
    by_split = result["aggregate_equal_record_by_split"]["evaluation"]["reception"]
    assert by_split["metrics"] == aggregate["metrics"]


def test_rejects_prefix_support_at_or_after_first_scored_window():
    mapping = _mapping()
    mapping["tracks"][0]["training_alias_points"][0]["support_center_utc_ns"] = 10_000_000_000
    with pytest.raises(ValueError, match="strictly earlier"):
        analyze({"schema": "rx-geometry-dataset/v1", "lanes": [_lane()]}, mapping)


def test_cli_requires_direct_mapping_hash_binding(tmp_path, monkeypatch):
    mapping = _mapping()
    mapping_path = tmp_path / "mapping.json"
    mapping_payload = json.dumps(mapping).encode()
    mapping_path.write_bytes(mapping_payload)
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [_lane()]}
    document["source_digests"] = {"mapping": "sha256:" + "0" * 64}
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(document))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rx_track_competition",
            "--dataset",
            str(dataset_path),
            "--mapping",
            str(mapping_path),
            "--output",
            str(tmp_path / "result.json"),
        ],
    )
    with pytest.raises(ValueError, match="directly bound"):
        main()
    document["source_digests"]["mapping"] = "sha256:" + hashlib.sha256(mapping_payload).hexdigest()
