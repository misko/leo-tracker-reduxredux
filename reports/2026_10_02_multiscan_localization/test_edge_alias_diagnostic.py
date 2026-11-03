import numpy as np
import pytest

from edge_alias_diagnostic import nearest_zero_pairs, summarize_pairs
from finite_set_likelihood import DEFAULT_ALIAS_HZ


def _row(probe, label, acquired, tracking, epoch):
    return {
        "probe_key": probe,
        "residual_class": label,
        "acquired_cfo_hz": acquired,
        "tracking_cfo_hz": tracking,
        "fractional_epoch_samples": epoch,
    }


def test_nearest_zero_uses_full_alias_and_circular_frame_epoch():
    half = DEFAULT_ALIAS_HZ / 2
    rows = [
        _row((1, 0, 2), "zero", 100.0, 100.0, 0.1),
        _row((1, 0, 2), "zero", 140.0, 140.0, 5.0),
        _row((1, 0, 2), "edge", 100.0 + half, 100.25 + DEFAULT_ALIAS_HZ, 9.9),
    ]
    result = nearest_zero_pairs(rows, frame_period_samples=10.0)
    assert result["no_zero_edge_rows"] == []
    assert result["tied_nearest_zero_families"] == []
    assert result["pairs"][0]["zero_rows"] == [0]
    assert result["pairs"][0]["final_circular_frequency_difference_hz"] == pytest.approx(0.25)
    assert result["pairs"][0]["acquired_half_alias_error_hz"] == pytest.approx(0.0)
    assert result["pairs"][0]["frame_epoch_difference_samples"] == pytest.approx(0.2)


def test_no_zero_and_exact_nearest_ties_are_preserved_as_family():
    rows = [
        _row((1, 0, 0), "edge", 0.0, 10.0, 0.0),
        _row((2, 0, 0), "zero", 0.0, 9.0, 0.0),
        _row((2, 0, 0), "zero", 0.0, 11.0, 0.0),
        _row((2, 0, 0), "edge", 0.0, 10.0, 0.0),
    ]
    result = nearest_zero_pairs(rows, frame_period_samples=10.0)
    assert len(result["pairs"]) == 1
    assert result["no_zero_edge_rows"] == [0]
    assert result["tied_nearest_zero_families"] == [
        {"edge_row": 3, "zero_rows": [1, 2], "frequency_difference_hz": 1.0}
    ]
    assert result["pairs"][0]["zero_rows"] == [1, 2]


def test_threshold_support_reports_catalog_overlap_without_collapsing_rows():
    rows = [
        _row((1, 0, 0), "zero", 0.0, 0.0, 0.0),
        _row((1, 0, 0), "edge", DEFAULT_ALIAS_HZ / 2, 0.5, 0.2),
        _row((2, 0, 0), "zero", 0.0, 100.0, 0.0),
        _row((2, 0, 0), "edge", DEFAULT_ALIAS_HZ / 2, 150.0, 0.4),
    ]
    masses = np.array([[0.6, 0.1], [0.5, 0.2], [0.1, 0.7], [0.2, 0.4]])
    pairing = nearest_zero_pairs(rows, frame_period_samples=10.0)
    result = summarize_pairs(
        pairing,
        masses,
        np.array([10, 20]),
        total_signal_mass=float(np.sum(masses)),
        sample_rate_hz=10_000_000,
    )
    one_hz = next(
        item for item in result["final_frequency_thresholds"]
        if item["final_frequency_threshold_hz"] == 1.0
    )
    assert one_hz["pair_count"] == 1
    assert one_hz["edge_signal_mass"] == pytest.approx(0.7)
    assert one_hz["posterior_catalog_overlap_mass"] == pytest.approx(0.6)
    assert one_hz["same_dominant_catalog_pair_count"] == 1
    assert one_hz["distinct_zero_row_count"] == 1
    quarter_sample = next(
        item for item in one_hz["joint_epoch_thresholds"]
        if item["frame_epoch_threshold_samples"] == 0.25
    )
    assert quarter_sample["pair_count"] == 1
    assert quarter_sample["edge_signal_mass"] == pytest.approx(0.7)


def test_tied_zero_raw_rows_are_summed_as_one_explicit_family():
    rows = [
        _row((1, 0, 0), "zero", 0.0, 0.0, 0.0),
        _row((1, 0, 0), "zero", DEFAULT_ALIAS_HZ, 0.0, 0.0),
        _row((1, 0, 0), "edge", DEFAULT_ALIAS_HZ / 2, 0.5, 0.1),
    ]
    masses = np.array([[0.3, 0.05], [0.3, 0.05], [0.5, 0.1]])
    pairing = nearest_zero_pairs(rows, frame_period_samples=10.0)
    result = summarize_pairs(
        pairing,
        masses,
        np.array([10, 20]),
        total_signal_mass=float(np.sum(masses)),
        sample_rate_hz=10_000_000,
    )
    one_hz = next(
        item for item in result["final_frequency_thresholds"]
        if item["final_frequency_threshold_hz"] == 1.0
    )
    assert one_hz["tied_zero_family_count"] == 1
    assert one_hz["paired_zero_signal_mass_with_reuse"] == pytest.approx(0.7)
    assert one_hz["posterior_catalog_overlap_mass"] == pytest.approx(0.6)
