import importlib.util
from pathlib import Path

import numpy as np
import pytest


MODULE = Path(__file__).with_name("proposal.py")
SPEC = importlib.util.spec_from_file_location("lag_proposal", MODULE)
assert SPEC is not None and SPEC.loader is not None
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


def _pilot(period: int) -> np.ndarray:
    rng = np.random.default_rng(2909 + period)
    # Amplitude structure gives power an independent timing cue.
    return (0.3 + rng.random(period)) * np.exp(2j * np.pi * rng.random(period))


def _signal(template: np.ndarray, rate: int, epoch: int, cfo_hz: float) -> np.ndarray:
    count = rate // 50
    signal = np.zeros(count, dtype=np.complex128)
    filled = np.zeros(count, dtype=bool)
    for start in P.frame_offsets(rate, count):
        valid = min(template.size, count - start)
        cells = (np.arange(valid) - epoch) % template.size
        signal[start : start + valid] = template[cells]
        filled[start : start + valid] = True
    time = np.arange(count) / rate
    signal *= np.exp(2j * np.pi * cfo_hz * time)
    # Rounded physical spacing can leave isolated cells outside a pilot frame.
    signal[~filled] = 0.0
    return signal


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000, 7_500_000, 10_000_000])
@pytest.mark.parametrize("cfo_hz", [-310_000.0, 0.0, 275_000.0])
def test_combined_peak_has_correct_epoch_and_lag_phase(rate: int, cfo_hz: float) -> None:
    period = round(rate / 750)
    epoch = period // 3 + 17
    template = _pilot(period)
    result = P.propose(_signal(template, rate, epoch, cfo_hz), template, rate)
    assert int(np.argmax(result["scores"]["combined"])) == epoch
    for lag in P.LAGS:
        assert int(np.argmax(result["scores"][f"lag{lag}"])) == epoch
        phase = np.angle(result["correlations"][f"lag{lag}"][epoch])
        expected = np.angle(np.exp(2j * np.pi * cfo_hz * lag / rate))
        assert abs(np.angle(np.exp(1j * (phase - expected)))) < 2e-3


def test_shift_sign_is_not_reversed() -> None:
    rate = 2_500_000
    period = round(rate / 750)
    template = _pilot(period)
    for epoch in (1, 91, period - 7):
        result = P.propose(_signal(template, rate, epoch, 123_456.0), template, rate)
        assert int(np.argmax(result["scores"]["combined"])) == epoch


def test_zero_input_is_finite_and_uninformative() -> None:
    rate = 2_500_000
    period = round(rate / 750)
    result = P.propose(np.zeros(rate // 50, dtype=complex), _pilot(period), rate)
    for group in result.values():
        for key, values in group.items():
            assert values.shape == (period,), key
            assert np.all(np.isfinite(values)), key
            assert np.all(values == 0), key


def test_requires_one_physical_template_period() -> None:
    with pytest.raises(ValueError, match="template length"):
        P.propose(np.ones(4096), np.ones(100), 2_500_000)
