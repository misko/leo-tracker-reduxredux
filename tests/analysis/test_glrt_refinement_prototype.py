"""Independent numerical oracles for the offline continuous-GLRT prototype."""

import numpy as np
import pytest

from leo.analysis.starlink.glrt_refinement_prototype import (
    continuous_glrt_score,
    continuous_peak,
    joint_refine,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame


@pytest.mark.parametrize("frequency", [137.19, -301.73, 113630.19, -113635.12])
def test_off_grid_tone_and_frequency_seam(frequency):
    step = 4.4e-6
    phases = np.exp(1j * np.array([0.13, 2.71, -1.81]))
    values = phases[:, None] * np.exp(2j * np.pi * frequency * np.arange(64) * step)
    peak = continuous_peak(values, step)
    error = (peak.frequency_hz - frequency + 0.5 / step) % (1 / step) - 0.5 / step
    assert abs(error) < 0.13
    assert peak.score == pytest.approx(1, abs=1e-8)
    assert peak.score >= peak.coarse_score


def test_multiframe_noisy_objective_matches_direct_phase_sum_and_dense_oracle():
    rng = np.random.default_rng(473)
    values = rng.normal(size=(7, 64)) + 1j * rng.normal(size=(7, 64))
    peak = continuous_peak(values, 4.4e-6)
    ceiling = np.sum(np.sum(abs(values), axis=1) ** 2)
    phase = np.exp(-2j * np.pi * peak.frequency_hz * np.arange(64) * 4.4e-6)
    direct = np.sum(abs(values @ phase) ** 2) / ceiling
    dense = np.max(np.sum(abs(np.fft.fft(values, n=65536, axis=1)) ** 2, axis=0)) / ceiling
    assert peak.score == pytest.approx(direct, abs=2e-14)
    assert peak.score >= dense - 1e-12


def test_zero_signal_has_no_invented_peak():
    peak = continuous_peak(np.zeros((3, 64)), 4.4e-6)
    assert peak.score == peak.frequency_hz == peak.runner_up_gap == 0


@pytest.mark.parametrize("fs", [2500000, 5000000, 10000000])
def test_joint_passes_preserve_score_and_recover_known_pilot_cfo(fs):
    template = np.asarray(qin_edge_pilot_frame(fs, "lower"))
    samples = np.zeros(fs // 50, dtype=complex)
    anchor, fraction, cfo = 173, 0.31, 40137.19
    for frame in range(14):
        start = anchor + round(frame * fs / 750)
        count = min(len(template), len(samples) - start)
        if count > 0:
            samples[start : start + count] += template[:count]
    samples = np.fft.ifft(
        np.fft.fft(samples) * np.exp(-2j * np.pi * np.fft.fftfreq(len(samples)) * fraction)
    )
    samples *= np.exp(2j * np.pi * cfo * np.arange(len(samples)) / fs)
    initial, _ = continuous_glrt_score(
        samples, fs, anchor=anchor, offset=0.1, conditioning_cfo_hz=39000, edge="lower"
    )
    offset, final, diagnostic = joint_refine(
        samples,
        fs,
        anchor=anchor,
        offset=0.1,
        conditioning_cfo_hz=39000,
        edge="lower",
        initial_score=initial,
    )
    assert all(h["after_score"] >= h["before_score"] for h in diagnostic["history"])
    assert abs(final.tracking_cfo_hz - cfo) < 10
    assert abs((offset - fraction) / fs) < 20e-9
    assert final.exact_score >= initial.exact_score
    assert final.tracking_cfo_hz == pytest.approx(
        final.residual_cfo_hz + diagnostic["history"][-1]["conditioning_cfo_hz"], abs=1e-8
    )
