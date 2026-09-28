import math

import pytest

from tools.rx_geometry_dataset import build_dataset


def fixtures():
    predictions = lambda mu: [  # noqa: E731
        {
            "source_window_id": "w",
            "role": "held_frequency",
            "window_start_utc_ns": 10,
            "window_end_utc_ns": 20,
            "prediction_utc_ns": 15,
            "predicted_hz": mu,
            "elevation_deg": -2.0,
            "visible": False,
            "los_enu_unit": {"east": 1.0, "north": 0.0, "up": 0.0},
        }
    ]
    bank = {
        "schema": "rx-training-candidate-bank/v1",
        "status": "complete",
        "tracks": [
            {
                "session_id": "s",
                "track_id": "a",
                "retained_catalogue_probability_mass": 0.8,
                "top_candidates": [
                    {
                        "catalog_number": 1,
                        "rank": 1,
                        "training_log_likelihood": 0.0,
                        "window_predictions": predictions(100.0),
                    },
                    {
                        "catalog_number": 2,
                        "rank": 2,
                        "training_log_likelihood": -1000.0,
                        "window_predictions": predictions(200.0),
                    },
                ],
            },
            {
                "session_id": "s",
                "track_id": "b",
                "retained_catalogue_probability_mass": 1.0,
                "top_candidates": [
                    {
                        "catalog_number": 3,
                        "rank": 1,
                        "training_log_likelihood": 0.0,
                        "window_predictions": predictions(300.0),
                    }
                ],
            },
        ],
    }
    mapping = {
        "schema": "rx-training-alias-mapping/v1",
        "status": "complete",
        "tracks": [
            {
                "session_id": "s",
                "track_id": "a",
                "receiver_id": 1,
                "channel": 1,
                "edge": "lower",
                "actual_rf_hz": 10.0,
                "canonical_scale": 2.0,
                "normalized_alias_spacing_hz": 20.0,
            },
            {
                "session_id": "s",
                "track_id": "b",
                "receiver_id": 0,
                "channel": 1,
                "edge": "lower",
                "actual_rf_hz": 10.0,
                "canonical_scale": 2.0,
                "normalized_alias_spacing_hz": 20.0,
            },
        ],
        "receiver_calibrations": [
            {
                "session_id": "s",
                "channel": 1,
                "edge": "lower",
                "actual_rf_hz": 10.0,
                "qualified": True,
                "bias_rx1_minus_rx0_hz": 3.0,
            }
        ],
    }
    partitions = {
        "schema": "rx-grouped-partition/v1",
        "recordings": [{"session_id": "s", "recording_split": "evaluation", "sample_rate_hz": 10}],
        "windows": [
            {
                "session_id": "s",
                "source_window_id": "w",
                "group_id": "g",
                "channel": 1,
                "edge": "lower",
                "recording_split": "evaluation",
                "sample_rate_hz": 10,
                "role": "held_frequency",
                "window_start_utc_ns": 10,
                "window_end_utc_ns": 20,
                "window_midpoint_utc_ns": 15,
            }
        ],
    }
    opportunity = {
        "source_window_id": "w",
        "window_start_utc_ns": 10,
        "window_end_utc_ns": 20,
        "source_window": {"session_id": "s", "channel": 1, "edge": "lower", "sample_rate_hz": 10},
        "receivers": {
            "rx0": {
                "receiver_status": "observed_candidate_absent",
                "actual_rf_hz": 10.0,
                "candidates": [],
            },
            "rx1": {
                "receiver_status": "observed_candidate_present",
                "actual_rf_hz": 10.0,
                "candidates": [
                    {
                        "candidate_id": "c",
                        "candidate_rank": 4,
                        "fractional_margin": 0.25,
                        "fractional_tracking_cfo_hz": 8.0,
                        "passed_fractional_margin_gate": True,
                    },
                    {"fractional_tracking_cfo_hz": 1000.0, "passed_fractional_margin_gate": False},
                ],
            },
        },
    }
    return bank, mapping, partitions, [opportunity]


def test_common_rx0_coordinates_log_priors_and_empty_receiver_are_preserved():
    lane = build_dataset(*fixtures())[0]
    assert lane["windows"][0]["observed"]["rx0"] == []
    assert lane["windows"][0]["observed"]["rx1"][0]["canonical_rx0_hz"] == 10.0
    predictions = lane["windows"][0]["predictions"]
    assert predictions[0]["mu_canonical_rx0_hz"] == 94.0
    assert predictions[0]["visible"] is False
    components = lane["components"]
    assert components[1]["log_prior"] == pytest.approx(math.log(0.4) - 1000.0)
    assert components[-1]["log_prior"] == pytest.approx(math.log(0.1))
    assert lane["accounting"]["windows_by_role"] == {"held_frequency": 1}


def test_duplicate_contract_keys_are_rejected():
    bank, mapping, partitions, opportunities = fixtures()
    with pytest.raises(ValueError, match="duplicate opportunity"):
        build_dataset(bank, mapping, partitions, opportunities * 2)
    mapping["tracks"].append(dict(mapping["tracks"][0]))
    with pytest.raises(ValueError, match="duplicate alias-mapping track"):
        build_dataset(bank, mapping, partitions, opportunities)


def test_malformed_view_is_an_explicit_exclusion():
    bank, mapping, partitions, opportunities = fixtures()
    opportunities[0]["receivers"]["rx1"]["receiver_status"] = "unqualified_timing"
    lane = build_dataset(bank, mapping, partitions, opportunities)[0]
    assert lane["windows"] == []
    assert lane["accounting"]["exclusions"] == {"unqualified_or_lane_mismatch": 1}
    assert lane["accounting"]["forecast_windows_by_role"] == {"held_frequency": 1}
    assert lane["accounting"]["excluded_windows_by_role"] == {"held_frequency": 1}


def test_malformed_passed_candidate_excludes_pair_and_small_mass_rounding_is_recorded():
    bank, mapping, partitions, opportunities = fixtures()
    bank["tracks"][1]["retained_catalogue_probability_mass"] = 1.0 + 5e-13
    opportunities[0]["receivers"]["rx1"]["candidates"][0]["candidate_id"] = ""
    lane = build_dataset(bank, mapping, partitions, opportunities)[0]
    assert lane["windows"] == []
    assert lane["accounting"]["exclusions"] == {"malformed_passed_candidate": 1}
    assert lane["retained_mass_rounding_corrections"] == [
        {"track_id": "b", "original": 1.0 + 5e-13, "bounded": 1.0}
    ]


def test_partition_groups_cannot_cross_roles():
    bank, mapping, partitions, opportunities = fixtures()
    partitions["windows"].append(
        {
            **partitions["windows"][0],
            "source_window_id": "another",
            "role": "reception",
        }
    )
    with pytest.raises(ValueError, match="group spans roles"):
        build_dataset(bank, mapping, partitions, opportunities)


def test_unqualified_bias_lane_is_reconciled_as_zero_window_lane():
    bank, mapping, partitions, opportunities = fixtures()
    mapping["receiver_calibrations"][0]["qualified"] = False
    lane = build_dataset(bank, mapping, partitions, opportunities)[0]
    assert lane["windows"] == []
    assert lane["components"] == []
    assert lane["accounting"]["forecast_windows_by_role"] == {"held_frequency": 1}
    assert lane["accounting"]["excluded_windows_by_role"] == {"held_frequency": 1}
    assert lane["accounting"]["exclusions"] == {"unqualified_receiver_bias": 1}
