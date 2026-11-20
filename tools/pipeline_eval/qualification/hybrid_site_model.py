"""Use exactly the same simulated Qin emission against two background models."""

from unittest.mock import patch

import numpy as np

from . import waveform_holdout_model as revised
from . import waveform_site_model as stock

SITE_BOX = (-5.0, -42.5)
SWEEPS = 96
RATE, SAMPLES = stock.RATE, stock.SAMPLES
pulse_bank = stock.pulse_bank
BACKGROUND_RMS = 530.0
ARMS = ("hybrid", "gaussian", "donor-only")


def schedule():
    visits = ORIGINAL_SCHEDULE()[: SWEEPS * 8]
    for row in visits:
        sweep, channel = divmod(row["visit"], 8)
        row["relative_counter"] = (sweep * 3125 + channel * stock.STRIDE_MS) * RATE // 1000
    return visits


ORIGINAL_SCHEDULE = stock.schedule


def make_scene(bank, causal, anchor, rng):
    # Background substitution isolates this experiment from optional waveform fades and bursts.
    with patch.multiple(stock, SITE_BOX=SITE_BOX, schedule=schedule):
        return stock.make_scene(revised.changed_bank(bank, causal), causal, anchor, rng)


def plant_iq(visit, profile, frame):
    signal = np.zeros((SAMPLES, 2, 2), dtype=np.float32)
    rng = np.random.default_rng(visit["sample_seed"])
    time = (stock.INDEX - (SAMPLES - 1) / 2) / profile["sample_rate_truth_hz"]
    for rx, p in enumerate(visit["planted"]):
        if p is None:
            continue
        epoch, period = p["epoch"], p["period"]
        pilot = stock.pulse(frame, epoch, period)
        pilot += (0.11 + 0.065j) * stock.pulse(frame, epoch + 1.2 + 0.3 * rx, period)
        phase = time * p["actual_cfo_hz"] + 0.5 * p["slope_hz_s"] * time**2 + rng.random()
        wave = p["amplitude"] * pilot * np.exp(2j * np.pi * phase)
        signal[:, rx, :] = np.column_stack((wave.real, wave.imag))
    return signal


def background(raw, seed):
    if raw.shape != (SAMPLES, 2, 2) or raw.dtype != np.dtype("<i2"):
        raise ValueError("background must be full dual CI16 at the fixed geometry")
    real = raw.astype(np.float32)
    real -= real.mean(axis=0, dtype=np.float64)
    sigma = float(np.sqrt(np.mean(real * real, dtype=np.float64)))
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("a valid donor window must have finite nonzero recorded component power")
    gain = BACKGROUND_RMS / sigma
    real *= gain
    per_component = np.sqrt(np.mean(real * real, axis=0, dtype=np.float64))
    synthetic = np.random.default_rng(seed ^ 0xFFAD8972CD542ED1).standard_normal(
        real.shape, dtype=np.float32
    )
    synthetic *= per_component
    return (
        real,
        synthetic,
        dict(original_rms=sigma, gain=gain, matched_component_rms=per_component.tolist()),
    )


def quantize(values):
    return np.clip(np.rint(values), -32768, 32767).astype("<i2")


def mixes(raw, emission, seed):
    real, synthetic, receipt = background(raw, seed)
    return {
        "hybrid": quantize(real + emission),
        "gaussian": quantize(synthetic + emission),
        "donor-only": quantize(real),
    }, receipt
