from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

MODULE_PATH = Path(__file__).parents[1] / "decision_band.py"
SPEC = importlib.util.spec_from_file_location("decision_band", MODULE_PATH)
assert SPEC and SPEC.loader
decision_band = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = decision_band
SPEC.loader.exec_module(decision_band)


@pytest.mark.parametrize("rate", [5_000_000, 7_500_000, 10_000_000])
def test_filter_geometry_has_exact_delay_and_boundary(rate):
    config = decision_band.default_config()
    geometry = decision_band.filter_geometry(rate, config)
    factor = rate // decision_band.DECISION_RATE_HZ
    assert geometry == {
        "factor": factor,
        "taps": 40 * factor + 1,
        "group_delay_source_samples": 20 * factor,
        "complete_support_decision_sample": 40,
        "fractional_valid_start_decision_sample": 42,
    }


@pytest.mark.parametrize("rate", [5_000_000, 7_500_000, 10_000_000])
def test_anti_alias_filter_passes_pilot_band_and_rejects_alias_tone(rate):
    config = decision_band.default_config()
    taps = decision_band.q15_coefficients(
        rate, beta=config["filter_beta"], span_outputs=config["filter_span_outputs"]
    ).astype(np.float64) / 32768
    frequencies = np.array([750_000.0, 1_750_000.0])
    phase = np.exp(-2j * np.pi * np.outer(frequencies / rate, np.arange(len(taps))))
    response = np.abs(phase @ taps)
    assert response[0] > 0.98
    assert response[1] < 3e-4


def test_group_delay_maps_decision_timing_to_source_coordinates():
    rate = 10_000_000
    group_delay = 80
    window, epoch, offset = 3, 211, 0.25
    mapped = decision_band.source_time_seconds(
        window, epoch, offset, rate, decision_band.DECISION_RATE_HZ, group_delay
    )
    expected_source_sample = 4 * (window * 50_000 + epoch + offset) - group_delay
    assert mapped == expected_source_sample / rate


def test_native_5m_baseline_epoch_maps_without_decimation_factor():
    mapped = decision_band.source_time_seconds(
        2,
        500,
        -0.25,
        5_000_000,
        5_000_000,
        0,
    )
    assert mapped == pytest.approx((2 * 100_000 + 500 - 0.25) / 5_000_000)


def test_boundary_excludes_fractional_search_without_full_filter_support():
    assert not decision_band.candidate_supported(0, 1, True, 0)
    assert decision_band.candidate_supported(0, 2, True, 0)
    assert not decision_band.candidate_supported(0, 41, True, 40)
    assert decision_band.candidate_supported(0, 42, True, 40)
    assert decision_band.candidate_supported(1, 0, True, 40)
    assert not decision_band.candidate_supported(1, 0, False, 40)


def test_circular_timing_match_crosses_pilot_period_boundary():
    period = decision_band.PILOT_PERIOD_SECONDS
    delta = decision_band.circular_difference_seconds(period - 0.5e-6, 0.5e-6)
    assert delta == pytest.approx(-1e-6)


def fake_result(*, candidate_count=1, margin=0.025, fractional_complete=True):
    candidate = SimpleNamespace(
        fractional_complete=int(fractional_complete),
        epoch=100,
        fractional_offset_samples=0.0,
        exact_score=0.5,
        control_score=0.5 - margin,
        margin=margin,
        tracking_cfo_hz=1234.0,
    )
    confirmation = SimpleNamespace(candidate_count=candidate_count, candidates=[candidate])
    return SimpleNamespace(confirmation_window_mask=1, confirmations=[confirmation])


def test_primary_margin_is_strict_and_zero_candidate_is_evaluated_negative():
    common = dict(
        source_rate_hz=2_500_000,
        analysis_rate_hz=2_500_000,
        group_delay_source_samples=0,
        complete_support_decision_sample=0,
        exact_threshold=0.175,
        margin_threshold=0.025,
    )
    boundary = decision_band.detection_from_result(fake_result(), **common)
    assert not boundary.detected
    above = decision_band.detection_from_result(fake_result(margin=0.0250001), **common)
    assert above.detected
    absent = decision_band.detection_from_result(fake_result(candidate_count=0), **common)
    assert not absent.detected
    assert absent.evaluation_status == "evaluated_no_candidate"


def test_delay_corrected_source_window_can_precede_raw_detector_window():
    timing = decision_band.source_time_seconds(
        1, 0, 0.0, 10_000_000, 2_500_000, 80
    )
    assert int(timing * 50) == 0


def test_changed_config_is_rejected_under_same_schema():
    config = decision_band.default_config()
    config["margin_threshold"] = 0.01
    with pytest.raises(ValueError, match="sealed design"):
        decision_band.validate_config(config, split="dev", dataset_sha256="abc")


def test_validation_requires_post_development_freeze():
    with pytest.raises(ValueError, match="post-development freeze"):
        decision_band.validate_config(
            decision_band.default_config(), split="validation", dataset_sha256="abc"
        )


def test_config_limits_recall_claim_to_matched_native_rates():
    scope = decision_band.default_config()["scope"]
    assert scope["recall_rates_hz"] == [2_500_000, 5_000_000]
    assert scope["descriptive_only_rates_hz"] == [7_500_000, 10_000_000]
