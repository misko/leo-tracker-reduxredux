from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking


def test_disjoint_validation_phase_does_not_train_its_own_correction():
    size, rate = 1024, 1024.0
    frequencies = np.fft.fftshift(np.fft.fftfreq(size, 1 / rate))
    time = np.arange(8 * size) / rate
    a = np.exp(2j * np.pi * frequencies[160] * time)
    b = np.exp(2j * np.pi * frequencies[224] * time)
    model = SimpleNamespace(
        frequency_hz=frequencies,
        channel_transfer=np.ones(size, complex),
        reference_sample=0,
        relative_cfo_hz=0,
        relative_cfo_rate_hz_s=0,
    )
    base = frequency_held_out_tracking(
        np.column_stack((a + b, (a + b) * np.exp(0.7j))), rate, model, block_samples=size
    )
    changed = frequency_held_out_tracking(
        np.column_stack((a + b, a * np.exp(0.7j) + b * np.exp(1.7j))),
        rate,
        model,
        block_samples=size,
    )
    assert base["tracked"]["phase_rad"] == pytest.approx(0, abs=1e-6)
    assert changed["tracked"]["phase_rad"] == pytest.approx(1, abs=1e-6)
    assert changed["rows"][0]["training_band_phase_rad"] == pytest.approx(
        base["rows"][0]["training_band_phase_rad"], abs=1e-6
    )
