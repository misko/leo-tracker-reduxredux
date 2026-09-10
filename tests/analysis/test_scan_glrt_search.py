"""Known transformations and bounded timing searches used by the offline study."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from replay_scan_glrt_search import alias_difference, dense_timing, frequency_shift
from summarize_scan_glrt_search import common_metrics, conditional_match


@pytest.mark.parametrize("fs", [2500000, 5000000])
@pytest.mark.parametrize("shift", [-301, 137])
def test_known_frequency_rotation_preserves_power_and_has_correct_phase(fs, shift):
    iq = np.array([1 + 2j] * 2000)
    shifted = frequency_shift(iq, fs, shift)
    assert abs(shifted) == pytest.approx(abs(iq))
    measured = np.angle(shifted[1:] * np.conj(shifted[:-1])) * fs / (2 * np.pi)
    assert measured == pytest.approx(np.full(1999, shift))


@pytest.mark.parametrize("step", [0.5, 0.25, 0.125])
def test_dense_search_recovers_an_off_grid_log_parabolic_peak(step):
    def score(x):
        return SimpleNamespace(exact_score=np.exp(-2 * (x - 0.173) ** 2))

    offset, result = dense_timing(score, step)
    assert offset == pytest.approx(0.173)
    assert result.exact_score == pytest.approx(1)


def test_dense_search_reports_an_unbracketed_peak():
    assert dense_timing(lambda x: SimpleNamespace(exact_score=np.exp(x)), 0.25) == (None, None)


def test_alias_difference_preserves_small_injected_frequency_error():
    assert alias_difference(1 / 4.4e-6 + 37) == pytest.approx(37)


def test_common_cubic_metric_exposes_smooth_bias_against_external_target():
    baseline = [{"t_s": float(i), "y_hz": 2 * i + 30.0} for i in range(30)]
    shifted = [{**r, "y_hz": r["y_hz"] + 150} for r in baseline]
    metric = common_metrics(shifted, baseline)
    assert metric["self_block_rms_hz"] < 1e-8
    assert metric["baseline_target_block_rms_hz"] == pytest.approx(150)


def test_conditional_matching_counts_a_missing_basin():
    row = {
        "original_cfo_hz": 1000.0,
        "candidates": [
            {
                "fractional_cfo_hz": 1001.0,
                "fractional_margin": 0.5,
                "epoch_distance_to_original_samples": 20,
                "fractional_exact_score": 0.6,
            }
        ],
    }
    assert conditional_match(row) is None
