import json
import subprocess

import numpy as np

from reports.ALGO08.v3 import repeat_fold_bank as bank


def folded_period(weighted, residue, lift):
    repeats, period = weighted.shape
    k = np.arange(period)
    inter = np.exp(-2j * np.pi * residue * np.arange(repeats))
    intra = np.exp(-2j * np.pi * residue * k / period)
    return np.fft.fft((inter @ weighted) * intra)[(k + lift) % period]


def test_repeat_spectrum_matches_signed_correlation_with_wrap_and_gap():
    rng = np.random.default_rng(8011)
    repeats, period = 3, 64
    residue = 1 / 3
    time = np.arange(repeats * period) / period
    pilot = np.zeros(period, complex)
    pilot[:23] = rng.choice([1, -1, 1j, -1j], size=23)
    delay = period - 3
    waveform = np.tile(np.roll(pilot, delay), repeats)
    weighted = []
    for lift in (-13, 17):
        carrier = np.exp(2j * np.pi * (residue + lift) * time)
        samples = (waveform * carrier).reshape(repeats, period)
        repeat_cross = np.vdot(samples[0], samples[1]) / np.vdot(samples[0], samples[0])
        np.testing.assert_allclose(repeat_cross, np.exp(2j * np.pi * residue), atol=2e-14)
        samples[1, -10:] = 0
        spectrum = folded_period(samples, residue, lift)
        response = np.fft.ifft(spectrum * np.conj(np.fft.fft(pilot)))
        demodulated = samples.ravel() / carrier
        direct = [np.vdot(np.tile(np.roll(pilot, d), repeats), demodulated) for d in range(period)]
        np.testing.assert_allclose(response, direct, atol=3e-13)
        assert np.argmax(abs(response)) == delay
        opposite = 17 if lift == -13 else -13
        wrong = np.fft.ifft(folded_period(samples, residue, opposite) * np.conj(np.fft.fft(pilot)))
        assert abs(wrong[delay]) < abs(response[delay]) * 0.25
        weighted.append(samples)
    assert not np.allclose(*weighted)


def test_a_coherent_sum_can_erase_individually_visible_frames():
    pilot = np.array([1, -1j, -1, 1j])
    rotated = np.exp(2j * np.pi * np.arange(3) / 3)[:, None] * pilot
    np.testing.assert_allclose(folded_period(rotated, 0, 0), 0, atol=2e-15)
    np.testing.assert_allclose(abs(rotated @ np.conj(pilot)), 4)
    assert abs(np.vdot(pilot, np.fft.ifft(folded_period(rotated, 1 / 3, 0)))) > 10


def test_prespecified_rows_and_dense_cost():
    assert bank.lift_cover(250) == (6400, 37, 173)
    assert bank.lift_cover(750) == (2133, 13, 165)
    assert bank.lift_cover(750, 305) == (2133, 1, 2133)
    assert bank.arithmetic(10_000, 2, 173)["real_alias_additions"] == 1_730_000
    price = json.loads((bank.HERE / "measurements" / "short-primary-fusion-price.json").read_bytes())
    assert round(bank.dense_budget(price, bank.GRID_STAGES)["available_us_per_call"], 1) == 113.3
    assert round(bank.dense_budget(price, bank.FRONT_STAGES)["available_us_per_call"], 1) == 356.0


def test_native_lift_decimation_matches_direct_signed_dot_products(tmp_path):
    binary = tmp_path / "repeat_fold_check"
    subprocess.run(["cc", *bank.BUILD_FLAGS, bank.HERE / "repeat_fold_bank.c", "-lfftw3f", "-lm",
                    "-o", binary], check=True)
    assert float(subprocess.check_output([binary, "--check"])) < 1e-4
