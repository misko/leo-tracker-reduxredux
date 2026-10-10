"""Synthetic frequency injection; no acquisition or positioning inputs."""

import importlib.util
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_10_09_position_error_iter120/partial_signal.py"
spec = importlib.util.spec_from_file_location("iter120_signal_frozen", SOURCE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
DELTA_HZ = 1 / (512 * 4.4e-6)


def signal(cutoff_s, phase_bins, *, amplitude, seed, noise_rms=1):
    if not np.isfinite(phase_bins) or not np.isfinite(noise_rms) or noise_rms < 0:
        raise ValueError("invalid injection")
    clean, occupancy = base.signal(cutoff_s, amplitude=amplitude, noise_rms=0, seed=seed)
    # Ramp and binary support mask commute. Apply only to signal, never noise.
    ramp = np.exp(2j * np.pi * phase_bins * DELTA_HZ * np.arange(len(clean)) / 2_500_000)
    rng = np.random.default_rng(seed)
    noise = (
        noise_rms / np.sqrt(2) * (rng.normal(size=len(clean)) + 1j * rng.normal(size=len(clean)))
    )
    return clean * ramp + noise, occupancy
