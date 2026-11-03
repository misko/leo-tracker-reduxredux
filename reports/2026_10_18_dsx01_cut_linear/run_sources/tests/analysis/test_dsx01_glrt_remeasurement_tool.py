"""Parity to the public GLRT and independent frequency/chirp controls."""

import numpy as np
import pytest
from dsx01_glrt_remeasurement import evaluate

from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
from leo.analysis.starlink.templates import qin_edge_pilot_frame


def recording(*, frequency=137.5, rate=0.0, phases=False):
    fs, epoch = 2_500_000, 700
    values = np.zeros(50000, dtype=np.complex128)
    template = qin_edge_pilot_frame(fs, "lower")
    rng = np.random.default_rng(42)
    for frame in range(15):
        start = epoch + round(frame * fs / 750)
        stop = min(len(values), start + len(template))
        if stop <= start:
            break
        values[start:stop] = template[: stop - start] * np.exp(
            1j * rng.uniform(-np.pi, np.pi) if phases else 0
        )
    t = np.arange(len(values)) / fs
    values *= np.exp(2j * np.pi * (frequency * t + 0.5 * rate * (t - 0.010) ** 2))
    return values


@pytest.mark.parametrize("fraction", [0.0, -0.27, 0.35])
def test_64_symbol_score_and_frequency_match_public_oracle(fraction):
    iq = recording()
    legacy = conditioned_glrt64_score(
        iq,
        2_500_000,
        epoch_sample=700,
        fractional_epoch_offset_samples=fraction,
        acquired_cfo_hz=0,
        edge="lower",
        glrt_size=512,
    )
    research = evaluate(iq, 700, fraction, 0, "lower", size=512, limit=1 / 8.8e-6)["glrt64"]
    assert research["exact_score"] == pytest.approx(legacy.exact_score, abs=1e-10)
    assert research["control_score"] == pytest.approx(legacy.control_score, abs=1e-10)
    assert research["residual_cfo_hz"] == pytest.approx(legacy.residual_cfo_hz, abs=1e-6)


def test_finer_grid_removes_frequency_quantization_with_independent_frame_phases():
    iq = recording(frequency=137.5, phases=True)
    result = evaluate(iq, 700, 0, 0, "lower")
    for method in ("glrt64", "glrt300", "midpoint300"):
        assert result[method]["accepted"]
        assert result[method]["residual_cfo_hz"] == pytest.approx(137.5, abs=14)


def test_midpoint_line_recovers_large_receiver_transient():
    result = evaluate(recording(frequency=-150, rate=-30000, phases=True), 700, 0, 0, "lower")
    assert result["midpoint300"]["accepted"]
    assert result["midpoint300"]["residual_cfo_hz"] == pytest.approx(-150, abs=14)
    assert result["midpoint300"]["rate_hz_s"] == pytest.approx(-30000, abs=1500)


def test_unrelated_noise_does_not_pass_known_pilot_controls():
    rng = np.random.default_rng(77)
    noise = rng.normal(size=50000) + 1j * rng.normal(size=50000)
    result = evaluate(noise, 700, 0, 0, "lower")
    assert not any(v["accepted"] for v in result.values())
