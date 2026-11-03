import copy

import numpy as np
import pytest

from tools.rx_temporal_alignment import METRICS, aggregate_rows, analyze, lane_reception_origins


def _dataset():
    def window(window_id, role, time_ns, observed, visible=(True, True)):
        return {
            "source_window_id": window_id,
            "role": role,
            "prediction_utc_ns": time_ns,
            "observed": {
                "rx0": [{"canonical_rx0_hz": value} for value in observed[0]],
                "rx1": [{"canonical_rx0_hz": value} for value in observed[1]],
            },
            "predictions": [
                {
                    "track_id": "track",
                    "catalog_number": 1,
                    "mu_canonical_rx0_hz": 100.0,
                    "visible": visible[0],
                },
                {
                    "track_id": "track",
                    "catalog_number": 2,
                    "mu_canonical_rx0_hz": 9_900.0,
                    "visible": visible[1],
                },
            ],
        }

    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "recording_split": "calibration",
                "lane": {"session_id": "s", "channel": 1},
                "alias_period_hz": 10_000.0,
                "components": [
                    {
                        "kind": "track_candidate",
                        "track_id": "track",
                        "catalog_number": 1,
                        "log_prior": np.log(0.25),
                    },
                    {
                        "kind": "track_candidate",
                        "track_id": "track",
                        "catalog_number": 2,
                        "log_prior": np.log(0.75),
                    },
                    {"kind": "other", "log_prior": None},
                ],
                "windows": [
                    window("r0", "reception", 1_000_000_000, ([120.0], [])),
                    window(
                        "h0",
                        "held_frequency",
                        66_000_000_000,
                        ([4_900.0], [100.0]),
                        (False, True),
                    ),
                ],
            }
        ],
    }


def _transfer():
    lane = {"session_id": "s", "channel": 1}

    def evaluation(arm):
        return {
            "lanes": [
                {
                    "lane": lane,
                    "window_presence": [0.2 if arm == "D" else 0.3, 0.4 if arm == "D" else 0.5],
                    "windows": [
                        {
                            "source_window_id": "r0",
                            "role": "reception",
                            "prediction_utc_ns": 1_000_000_000,
                            "relative_log_score": 1.0 if arm == "D" else 2.0,
                        },
                        {
                            "source_window_id": "h0",
                            "role": "held_frequency",
                            "prediction_utc_ns": 66_000_000_000,
                            "relative_log_score": 3.0 if arm == "D" else 4.0,
                        },
                    ],
                }
            ]
        }

    return {
        "schema": "rx-geometry-temporal-transfer/v1",
        "status": "complete",
        "folds": [
            {
                "held_session": "s",
                "families": {
                    "within": {"evaluations": {"D": evaluation("D"), "T": evaluation("T")}}
                },
            }
        ],
    }


def test_periodic_alignment_prior_weight_visibility_and_empty_receiver() -> None:
    result = analyze(_dataset(), _transfer())
    reception, held = result["windows"]
    assert reception["prior_probability_nearest_le_500hz_rx0"] == pytest.approx(1.0)
    assert reception["prior_probability_nearest_le_1500hz_rx1"] == 0.0
    assert reception["candidate_count_rx1"] == 0
    # RX1's 100 Hz point is 200 Hz across the circle from nominee two at 9900 Hz;
    # nominee one is invisible and contributes zero without renormalization.
    assert held["visible_prior_mass"] == pytest.approx(0.75)
    assert held["prior_probability_nearest_le_500hz_rx1"] == pytest.approx(0.75)
    assert held["prior_probability_nearest_le_1500hz_rx0"] == 0.0
    assert held["elapsed_bin_s"] == "60-90"


def test_transfer_scores_and_presence_join_by_window_id() -> None:
    result = analyze(_dataset(), _transfer())
    by_id = {row["source_window_id"]: row for row in result["windows"]}
    assert by_id["r0"]["D_presence_probability"] == pytest.approx(0.2)
    assert by_id["r0"]["T_relative_log_score"] == pytest.approx(2.0)
    assert by_id["h0"]["D_relative_log_score"] == pytest.approx(3.0)
    aggregate = result["aggregate_equal_record"]["held_frequency:60-90"]
    assert aggregate["recordings_with_windows"] == 1
    assert aggregate["windows"] == 1


def test_duplicate_or_missing_join_population_is_rejected() -> None:
    duplicate = _dataset()
    duplicate["lanes"][0]["windows"][1]["source_window_id"] = "r0"
    with pytest.raises(ValueError, match="duplicate dataset"):
        analyze(duplicate, _transfer())
    missing = _transfer()
    missing["folds"][0]["families"]["within"]["evaluations"]["T"]["lanes"][0]["windows"].pop()
    missing["folds"][0]["families"]["within"]["evaluations"]["T"]["lanes"][0][
        "window_presence"
    ].pop()
    with pytest.raises(ValueError, match="D/T transfer window populations differ"):
        analyze(_dataset(), missing)


def test_inputs_are_immutable() -> None:
    document, transfer = _dataset(), _transfer()
    document_before, transfer_before = copy.deepcopy(document), copy.deepcopy(transfer)
    analyze(document, transfer)
    assert document == document_before
    assert transfer == transfer_before


def test_elapsed_origin_is_separate_for_each_lane() -> None:
    document = _dataset()
    second = copy.deepcopy(document["lanes"][0])
    second["lane"]["channel"] = 2
    for window in second["windows"]:
        window["prediction_utc_ns"] += 100_000_000_000
    document["lanes"].append(second)
    origins = lane_reception_origins(document)
    assert origins[("s", '{"channel":1,"session_id":"s"}')] == 1_000_000_000
    assert origins[("s", '{"channel":2,"session_id":"s"}')] == 101_000_000_000


def test_role_total_uses_equal_record_not_pooled_window_weight() -> None:
    rows = []
    for session_id, values in (("a", [0.0]), ("b", [10.0, 10.0, 10.0])):
        for value in values:
            row = {
                "session_id": session_id,
                "role": "reception",
                "elapsed_bin_s": "0-30",
            }
            row.update({metric: value for metric in METRICS})
            rows.append(row)
    aggregate = aggregate_rows(rows, {"a", "b"})["reception:all"]
    assert aggregate["windows"] == 4
    assert aggregate["recordings_with_windows"] == 2
    assert aggregate["equal_record_mean"]["D_relative_log_score"] == pytest.approx(5.0)
