from types import SimpleNamespace

import numpy as np
import pytest
from export_ds11 import (
    ALIAS_SPACING_HZ,
    REFERENCE_RF_HZ,
    conditional_initial,
    frozen_capture_entry,
    geometry_nodes,
    ordered_review_candidates,
    raw_arrays,
    track_rows,
)


def test_geometry_nodes_preserve_standard_domain_and_extend_long_scans():
    standard = geometry_nodes(299.75)
    assert standard[0] == -11
    assert standard[-1] == 311
    assert np.allclose(np.diff(standard), 0.25)
    extended = geometry_nodes(312.1)
    assert extended[-1] == 323.25


def test_candidate_order_prioritizes_first_choices_then_rank_and_support():
    reviews = [
        {
            "observation_count": 20,
            "candidates": [
                {"rank": 1, "catalog_number": 30},
                {"rank": 2, "catalog_number": 10},
                {"rank": 3, "catalog_number": 20},
            ],
        },
        {
            "observation_count": 40,
            "candidates": [
                {"rank": 1, "catalog_number": 40},
                {"rank": 2, "catalog_number": 10},
                {"rank": 3, "catalog_number": 50},
            ],
        },
    ]
    ordered, statistics = ordered_review_candidates(reviews)
    assert ordered == [40, 30, 10, 50, 20]
    assert statistics[10]["support"] == 60
    assert statistics[40]["first_support"] == 40


def test_conditional_initial_uses_folded_rank_one_receiver_consensus():
    rf_hz = REFERENCE_RF_HZ
    product = {
        "tracklets": [
            {"tracklet_id": "a", "receiver_id": 0, "actual_rf_hz": rf_hz},
            {"tracklet_id": "b", "receiver_id": 0, "actual_rf_hz": rf_hz},
            {"tracklet_id": "c", "receiver_id": 1, "actual_rf_hz": rf_hz},
        ],
        "track_reviews": [
            {
                "tracklet_id": "a",
                "observation_count": 10,
                "candidates": [{"rank": 1, "catalog_number": 1, "fitted_offset_hz": 5.0}],
            },
            {
                "tracklet_id": "b",
                "observation_count": 30,
                "candidates": [
                    {
                        "rank": 1,
                        "catalog_number": 2,
                        "fitted_offset_hz": ALIAS_SPACING_HZ + 20.0,
                    }
                ],
            },
            {
                "tracklet_id": "c",
                "observation_count": 10,
                "candidates": [{"rank": 1, "catalog_number": 3, "fitted_offset_hz": -7.0}],
            },
        ],
    }
    initial, receipt = conditional_initial(product, candidate_count=3)
    np.testing.assert_allclose(initial, [0, 0, 20, 0, -7, 0, 0, 0, 0])
    assert receipt["conditional_on_known_site_candidate_reviews"] is True


def test_track_rows_map_public_point_ids_to_complete_raw_rows():
    candidates = [
        SimpleNamespace(candidate_id="b", support_center_utc_ns=20),
        SimpleNamespace(candidate_id="a", support_center_utc_ns=10),
        SimpleNamespace(candidate_id="unused", support_center_utc_ns=15),
    ]
    tracklet = SimpleNamespace(
        tracklet_id="track",
        points=(SimpleNamespace(candidate_id="b"), SimpleNamespace(candidate_id="a")),
        lane_key=(3, "lower", 1, 11.2e9),
    )
    trajectory = SimpleNamespace(tracklets=(tracklet,))
    reviews = [{"tracklet_id": "track", "observation_count": 2}]
    tracks, receipt = track_rows(candidates, trajectory, reviews)
    assert tracks[0]["rows"] == [1, 0]
    assert tracks[0]["candidate_indices"] == list(range(64))
    assert receipt["unique_raw_rows"] == 2


def test_raw_arrays_keep_every_candidate_and_group():
    candidates = [
        SimpleNamespace(
            candidate_id=f"candidate-{index}",
            source_group_id=f"group-{index // 2}",
            support_center_utc_ns=1_000_000_000 + index,
            measured_cfo_hz=float(index),
            actual_rf_hz=10e9 + index,
            receiver_id=index % 2,
            channel=index + 1,
            margin=0.1 + index,
        )
        for index in range(5)
    ]
    arrays, receipt = raw_arrays(candidates, 1_000_000_000)
    assert len(arrays["times"]) == 5
    assert receipt["projected_candidate_count"] == 5
    assert receipt["source_group_count"] == 3
    assert set(arrays["group"]) == {0, 1, 2}


def test_frozen_capture_entry_requires_one_bound_session():
    manifest = {"dataset_id": "DS11", "captures": [{"session_id": "one"}]}
    assert frozen_capture_entry("one", manifest)["session_id"] == "one"
    with pytest.raises(ValueError, match="exactly one"):
        frozen_capture_entry("missing", manifest)
