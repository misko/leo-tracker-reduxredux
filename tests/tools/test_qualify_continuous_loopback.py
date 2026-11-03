import numpy as np
import pytest

from tools.qualify_continuous_loopback import tone_metrics


def test_integer_tone_identifies_each_receiver_and_rail_contacts() -> None:
    time = np.arange(50_000) / 2_500_000
    signal = np.exp(2j * np.pi * 100_000 * time)
    samples = np.empty((50_000, 2, 2), dtype=np.int16)
    for rx, amplitude in enumerate((1000, 500)):
        samples[:, rx, 0] = np.rint(signal.real * amplitude)
        samples[:, rx, 1] = np.rint(signal.imag * amplitude)
    metrics = tone_metrics(samples)
    assert all(row["peak_hz"] == 100_000 and row["tone_fraction"] > 0.999 for row in metrics)
    assert all(row["adc12_rail_contacts"] == 0 for row in metrics)
    samples[0, 1, 0] = -2048
    assert tone_metrics(samples)[1]["adc12_rail_contacts"] == 1


def test_partial_window_cannot_be_tone_qualified() -> None:
    with pytest.raises(ValueError, match="exact dual-RX"):
        tone_metrics(np.zeros((49_999, 2, 2), dtype=np.int16))
