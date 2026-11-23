from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def cyclic(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(path))
    return import_module("cyclic_carrier_trial")


def test_unknown_timing_changes_phase_and_preserves_power(cyclic):
    time = np.arange(128)
    pilot = np.exp(2j * np.pi * time * 6 / len(time)) + .5 * np.exp(-2j * np.pi * time * 12 / len(time))
    delayed = np.roll(pilot, 23)
    frequency = 17
    shifted = delayed * np.exp(2j * np.pi * time * frequency / len(time))
    reference = cyclic.spectrum(pilot * np.roll(pilot, -1))
    moved = cyclic.spectrum(shifted * np.roll(shifted, -1))
    np.testing.assert_allclose(abs(moved), np.roll(abs(reference), 2 * frequency), atol=1e-13)


def test_quadratic_noise_model_charges_weak_amplitudes(cyclic):
    known = cyclic.white_noise_line_power(1, 1200, .06)
    assert known == 48.
    assert cyclic.white_noise_line_power(.1, 1200, .06) == pytest.approx(known * .01)


def test_native_search_keeps_sign_when_spectral_line_wraps(cyclic, tmp_path):
    binary = tmp_path / "cyclic.so"
    cyclic.build(binary)
    scout = cyclic.Scout(binary, 16384)
    lines = np.zeros(16, dtype=np.intc)
    weights = np.zeros(16, dtype=np.float32)
    weights[0] = 1
    data = np.zeros((65536, 2, 2), dtype="<i2")
    try:
        for signed in (-1, 1):
            expected = signed * 775_321
            lines[0] = signed * 1700
            sideband = expected + lines[0] * 750 / 2
            wave = 3000 * np.exp(2j * np.pi * np.arange(len(data)) * sideband / cyclic.ADC)
            data[:, 1, 0], data[:, 1, 1] = np.rint(wave.real), np.rint(wave.imag)
            result = scout.measure(data, 1, signed * 50_000, lines, weights, repeats=1)
            assert abs(result["hz"][0] - expected) <= 2 * 5_000_000 / 16384 / 2
            assert len(result["hz"]) == 4
            assert all(abs(a - b) >= 10000 for i, a in enumerate(result["hz"]) for b in result["hz"][i + 1:])
    finally:
        scout.close()


def test_unverified_proposals_and_failed_residual_charge_full_fallback(cyclic):
    factor = [1, 0, 0., 440000, .1, 0.]
    four_hertz = [1200, 1300, 1400, 1500]
    evidence = {str(size): dict(match_rank=None, hz=four_hertz, cpu_ns=60000) for size in cyclic.SIZES}
    lane = dict(edge="upper", installed_cpu_ns=2500000,
                scans=[dict(factor=None, measures=evidence), dict(factor=factor, measures=evidence)])
    result = cyclic.summarize([lane])["16384"]
    assert result["groups"][0]["slots_without_matching_factor"] == 4
    assert result["groups"][1]["factors"] == 1
    assert result["oracle_fallback_lanes"] == 1
    assert result["scout_plus_oracle_fallback_ms_per_lane"] == pytest.approx(2.62)
