from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_multi_dwell_starlink_association.py"
    spec = importlib.util.spec_from_file_location("multi_dwell_starlink_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_ranking_uses_training_only() -> None:
    tool = _tool()
    rows = [
        {
            "catalog_number": 1,
            "train_residual_rms_hz": 10.0,
            "holdout_residual_rms_hz": 1_000.0,
        },
        {
            "catalog_number": 2,
            "train_residual_rms_hz": 11.0,
            "holdout_residual_rms_hz": 1.0,
        },
    ]

    ranked = tool._rank_evaluations(rows)

    assert ranked[0]["catalog_number"] == 1


def test_source_cohort_must_be_exactly_the_requested_strict_linear_order() -> None:
    tool = _tool()
    source = {
        "analysis_kind": "multi_dwell_degree1_only_report_rerun",
        "radio_polynomial_degrees": [1],
        "dwells": [{"session_id": "a"}, {"session_id": "b"}],
    }

    tool._validate_source_cohort(source, ("a", "b"))
    with pytest.raises(ValueError, match="cohort/order"):
        tool._validate_source_cohort(source, ("b", "a"))
    with pytest.raises(ValueError, match="strictly degree one"):
        tool._validate_source_cohort({**source, "radio_polynomial_degrees": [1, 2]}, ("a", "b"))


def test_scalar_null_can_only_support_the_same_shape_identity() -> None:
    tool = _tool()
    scalar = {
        "top_candidates": [
            {"catalog_number": 101, "object_name": "STARLINK-A"},
            {"catalog_number": 202, "object_name": "STARLINK-B"},
        ]
    }

    assert tool._scalar_shape_identity_agree(scalar, {"catalog_number": 101}) is True
    assert tool._scalar_shape_identity_agree(scalar, {"catalog_number": 202}) is False
    empty_scalar = {"top_candidates": []}
    assert tool._scalar_shape_identity_agree(empty_scalar, {"catalog_number": 101}) is False
    assert tool._scalar_shape_identity_agree(scalar, None) is False


def test_bounded_orbit_recovers_synthetic_curvature() -> None:
    tool = _tool()
    times = np.linspace(0.0, 20.0, 401)
    centered = times - 10.0
    true_doppler = -5_000.0 * centered + 8.0 * centered**2
    false_doppler = -5_000.0 * centered - 8.0 * centered**2
    series = tool.TrackSeries(times, true_doppler + 80_000.0 + 50.0 * centered)
    train = tool._temporal_split(times)

    true_result = tool._evaluate_prediction(
        series,
        times,
        true_doppler,
        train=train,
        maximum_drift_hz_s=200.0,
        epoch_bound_s=0.0,
    )
    false_result = tool._evaluate_prediction(
        series,
        times,
        false_doppler,
        train=train,
        maximum_drift_hz_s=200.0,
        epoch_bound_s=0.0,
    )
    linear = tool._linear_null(series, train)

    assert true_result["train_residual_rms_hz"] < 1e-6
    assert true_result["holdout_residual_rms_hz"] < 1e-6
    assert false_result["train_residual_rms_hz"] > 10.0
    assert linear["holdout_residual_rms_hz"] > true_result["holdout_residual_rms_hz"]


def test_temporal_split_reserves_chronological_holdout() -> None:
    tool = _tool()
    times = np.asarray([5.0, 1.0, 4.0, 0.0, 3.0, 2.0, 6.0, 7.0])

    train = tool._temporal_split(times, 0.5)

    assert set(times[train]) == {0.0, 1.0, 2.0, 3.0}
    assert set(times[~train]) == {4.0, 5.0, 6.0, 7.0}


def test_rf_frequency_evidence_checks_tags_if_and_path() -> None:
    tool = _tool()
    tagged_rf_hz = 10_709_687_500
    track = SimpleNamespace(
        path=SimpleNamespace(
            rf_frequency_hz=tagged_rf_hz,
            binding=SimpleNamespace(
                starlink_channel=1,
                starlink_edge="lower",
                tuned_center_frequency_hz=tagged_rf_hz - tool.STARLINK_LNB_LO_HZ,
            ),
        )
    )

    evidence = tool._rf_frequency_evidence(track)

    assert evidence["tag_minus_reconstructed_hz"] == 0
    assert evidence["tag_minus_path_hz"] == 0
    assert evidence["pilot_rf_half_width_hz"] == 937_500.0


def test_adjacent_tle_sensitivity_removes_affine_difference() -> None:
    tool = _tool()
    times = np.linspace(0.0, 10.0, 41)
    current_rate = np.zeros((1, times.size))
    previous_rate = np.asarray([0.01 + 0.0001 * times + 0.00001 * times**2])
    track = SimpleNamespace(path=SimpleNamespace(rf_frequency_hz=12.0e9))
    series = tool.TrackSeries(times, np.zeros(times.size))
    current_snapshot = SimpleNamespace(collected_utc_ns=200_000_000_000)
    previous_snapshot = SimpleNamespace(
        collected_utc_ns=100_000_000_000,
        digest="sha256:previous",
    )
    current_satellite = SimpleNamespace(element_epoch_utc_ns=190_000_000_000)
    previous_catalogue = SimpleNamespace(
        satellite_numbers=(7,), element_epoch_utc_ns=lambda: (90_000_000_000,)
    )

    result = tool._tle_snapshot_sensitivity(
        track,
        series,
        {"catalog_number": 7},
        {7: (0, current_satellite)},
        times,
        SimpleNamespace(range_rate_km_s=current_rate),
        current_snapshot,
        previous_snapshot,
        previous_catalogue,
        SimpleNamespace(range_rate_km_s=previous_rate),
        {7: 0},
    )

    assert result["available"] is True
    assert result["collection_separation_s"] == 100.0
    assert result["element_epoch_separation_s"] == 100.0
    assert result["raw_frequency_rms_hz"] > result["affine_removed_shape_rms_hz"]
    assert result["affine_removed_shape_rms_hz"] > 0.0
