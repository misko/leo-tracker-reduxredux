"""Known full-band alignment cases; generated signal is independent of estimator."""

from __future__ import annotations

import numpy as np


def make_case(*, noise_only=False, response=False, interference=False, seed=7331):
    rate = 2_500_000.0
    count = 300_000
    rng = np.random.default_rng(seed)
    # Long stationary complex realization with guard samples before taking the crop.
    size = 1 << 20
    frequencies = np.fft.fftfreq(size, 1 / rate)
    support = (frequencies > -450_000) & (frequencies < 950_000)
    spectrum = (rng.normal(size=size) + 1j * rng.normal(size=size)) * support
    source = np.fft.ifft(spectrum)
    scale = np.sqrt(np.mean(abs(source) ** 2))
    source /= scale
    delay = 2.375
    phase = 0.73
    cfo = -675_123.4
    drift = 480.0
    frequency_response = np.ones(size, complex)
    if response:
        coordinate = (frequencies - 250_000) / 700_000
        frequency_response = (1 + 0.15 * np.cos(2 * np.pi * coordinate)) * np.exp(
            0.25j * np.cos(np.pi * coordinate)
        )
    shifted = np.fft.ifft(
        spectrum / scale * np.exp(-2j * np.pi * frequencies * delay / rate) * frequency_response
    )
    start = 100_000
    time = np.arange(count) / rate
    left = source[start : start + count].copy()
    right = shifted[start : start + count] * np.exp(
        1j * (phase + 2 * np.pi * (cfo * time + drift * time**2 / 2))
    )
    if noise_only:
        left[:] = 0
        right[:] = 0
    noise_amplitude = 0.22 if not noise_only else 1.0
    left += noise_amplitude * (rng.normal(size=count) + 1j * rng.normal(size=count))
    right += noise_amplitude * (rng.normal(size=count) + 1j * rng.normal(size=count))
    if interference:
        # Independent receiver interferers, not shared tone truth.
        left += 2 * np.exp(2j * np.pi * 321_123 * time)
        right += 2 * np.exp(2j * np.pi * -51_987 * time)
    truth = {
        "sample_rate_hz": rate,
        "sample_count": count,
        "rx1_delay_samples": delay,
        "phase_at_visit_start_rad": phase,
        "cfo_at_visit_start_hz": cfo,
        "cfo_rate_hz_s": drift,
        "nonlinear_channel_response": response,
        "independent_interference": interference,
        "noise_only": noise_only,
        "seed": seed,
        "source_band_hz": [-450_000, 950_000],
        "delay_definition": "RX1 envelope is RX0 delayed +2.375 samples before modulation",
    }
    return np.column_stack((left, right)), rate, truth
