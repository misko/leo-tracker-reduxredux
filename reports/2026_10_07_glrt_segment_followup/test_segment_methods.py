"""Independent numerical oracles for shared-aperture segment and phase-kernel tests."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from segment_methods import (
    _phase_kernel_profile,
    score_at_frequency,
    score_bank,
    score_trials,
)


def noise(seed, shape):
    rng = np.random.default_rng(seed)
    return rng.normal(size=shape) + 1j * rng.normal(size=shape)


def segment_likelihood(raw, energy, length, frequency):
    """Solve each segment amplitude with least squares and compare residual energy."""
    total = np.sum(np.abs(raw) ** 2 / energy)
    residual_energy = 0.0
    for row in raw:
        for start in range(0, len(energy), length):
            support = slice(start, start + length)
            observed = row[support] / np.sqrt(energy[support])
            steering = (
                np.sqrt(energy[support])
                * np.exp(2j * np.pi * frequency * np.arange(start, start + length) * 4.4e-6)
            )[:, None]
            amplitude = np.linalg.lstsq(steering, observed, rcond=None)[0]
            residual = observed - steering @ amplitude
            residual_energy += np.vdot(residual, residual).real
    return (total - residual_energy) / total


@pytest.mark.parametrize("count,length", [(64, 8), (64, 16), (128, 32), (256, 64)])
def test_segment_matches_independent_residual_likelihood(count, length):
    raw = noise(10, (2, count))
    energy = np.linspace(0.3, 2.4, count)
    grid = np.fft.fftfreq(512, d=4.4e-6)
    oracle = np.array([segment_likelihood(raw, energy, length, frequency) for frequency in grid])
    actual = score_bank(
        raw, noise(11, raw.shape), exact_template_energy=energy, return_profiles=True
    )[f"segment{length}"]
    np.testing.assert_allclose(actual["exact_profile"], oracle, atol=5e-14)
    assert actual["score"] == pytest.approx(oracle.max(), abs=5e-14)
    assert actual["cfo_hz"] == grid[oracle.argmax()]


@pytest.mark.parametrize("count,length", [(64, 8), (128, 16), (256, 32)])
def test_phase_kernel_matches_direct_toeplitz_quadratic(count, length):
    raw = noise(12, (2, count))
    energy = np.linspace(0.4, 2.1, count)
    indexes = np.arange(count)
    kernel = np.exp(-np.abs(indexes[:, None] - indexes[None, :]) / length)
    grid = np.fft.fftfreq(512, d=4.4e-6)
    rotated = raw[None] * np.exp(
        -2j * np.pi * grid[:, None, None] * indexes[None, None, :] * 4.4e-6
    )
    oracle = np.einsum("bfi,ij,bfj->b", rotated.conj(), kernel, rotated, optimize=True).real
    oracle /= energy.sum() * np.sum(np.abs(raw) ** 2 / energy)
    actual = score_bank(
        raw, noise(13, raw.shape), exact_template_energy=energy, return_profiles=True
    )[f"phase_kernel{length}"]
    np.testing.assert_allclose(actual["exact_profile"], oracle, atol=5e-14)
    assert actual["cfo_hz"] == grid[oracle.argmax()]
    assert np.linalg.eigvalsh(kernel).min() > 0
    assert actual["exact_profile"].min() >= 0
    assert actual["exact_profile"].max() <= 1


def test_coherent_limit_of_phase_kernel_and_fourier_psd():
    raw = noise(14, (3, 64))
    power = (np.abs(np.fft.fft(raw, n=512, axis=-1)) ** 2).sum(axis=0, keepdims=True)
    correlation = np.fft.ifft(power, axis=-1)
    actual = _phase_kernel_profile(correlation, 64, np.inf, 512)
    np.testing.assert_allclose(actual, power, atol=1e-10)
    for length in (8, 16, 32):
        assert _phase_kernel_profile(correlation, 64, length, 512).min() >= 0


def test_original_coherent64_and_segment32_equivalence():
    path = Path(__file__).resolve().parents[1] / "2026_10_07_glrt_detector_comparison/methods.py"
    spec = importlib.util.spec_from_file_location("previous_glrt_comparison_methods", path)
    previous = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = previous
    spec.loader.exec_module(previous)
    raw, control = noise(15, (14, 64)), noise(16, (14, 64))
    kwargs = dict(
        exact_template_energy=np.linspace(0.2, 2.0, 64),
        control_template_energy=np.linspace(1.2, 0.7, 64),
    )
    old = previous.score_bank(raw, control, **kwargs)
    new = score_bank(raw, control, **kwargs)
    for old_name, new_name in (
        ("current_glrt64_margin", "current_coherent_margin"),
        ("gaussian_glrt64", "gaussian_coherent"),
        ("segmented_glrt32", "segment32"),
        ("gaussian_glrt64", "segment64"),
    ):
        for key, value in old[old_name].items():
            assert new[new_name][key] == pytest.approx(value, abs=5e-13)


@pytest.mark.parametrize("count", [64, 128, 256])
def test_batch_matches_scalar_and_inputs_immutable(count):
    exact, control = noise(17, (3, 14, count)), noise(18, (3, 14, count))
    exact.setflags(write=False)
    control.setflags(write=False)
    kwargs = dict(
        exact_template_energy=np.linspace(0.4, 3.1, count),
        control_template_energy=np.linspace(1.2, 2.1, count),
        return_profiles=True,
    )
    batch = score_trials(exact, control, **kwargs)
    for trial in range(3):
        scalar = score_bank(exact[trial], control[trial], **kwargs)
        for method in scalar:
            for key in scalar[method]:
                np.testing.assert_allclose(
                    batch[method][key][trial], scalar[method][key], atol=5e-14
                )


def test_phase_scale_and_frequency_symmetry():
    frequency = 23 / (512 * 4.4e-6)
    raw = np.ones((2, 128)) * np.exp(2j * np.pi * frequency * np.arange(128) * 4.4e-6)
    control = noise(19, raw.shape)
    original = score_bank(raw, control)
    rotated = score_bank(raw * 3 * np.exp(0.3j), control * 2 * np.exp(-0.9j))
    conjugated = score_bank(raw.conj(), control.conj())
    for method in original:
        assert original[method]["cfo_hz"] == pytest.approx(frequency)
        assert conjugated[method]["cfo_hz"] == pytest.approx(-frequency)
        for key in original[method]:
            assert rotated[method][key] == pytest.approx(original[method][key], abs=5e-13)


def test_fixed_frequency_never_remaximizes_either_channel():
    count = 64
    frequency = 19.2 / (512 * 4.4e-6)
    raw, control = noise(20, (2, count)), noise(21, (2, count))
    energy = np.linspace(0.3, 2.3, count)
    fixed = score_at_frequency(raw, control, frequency, exact_template_energy=energy)
    for length in (8, 16, 32, 64):
        exact_oracle = segment_likelihood(raw, energy, length, frequency)
        control_oracle = segment_likelihood(control, np.ones(count), length, frequency)
        item = fixed[f"segment{length}"]
        assert item["exact_score"] == pytest.approx(exact_oracle, abs=5e-14)
        assert item["control_score"] == pytest.approx(control_oracle, abs=5e-14)
        assert item["cfo_hz"] == item["control_cfo_hz"] == frequency
        assert fixed[f"segment{length}_margin"]["score"] == pytest.approx(
            exact_oracle - control_oracle, abs=5e-14
        )


@pytest.mark.parametrize("shape", [(3, 0, 64), (0, 14, 128), (3, 14, 256)])
def test_zero_and_empty_inputs(shape):
    zeros = np.zeros(shape, complex)
    results = score_trials(zeros, zeros, return_profiles=True)
    for item in results.values():
        assert all(np.all(value == 0) for value in item.values())


@pytest.mark.parametrize(
    "bad",
    [
        np.zeros((2, 64)),
        np.zeros((1, 2, 32)),
        np.full((1, 2, 64), np.nan),
        np.full((1, 2, 64), np.inf),
    ],
)
def test_invalid_matrices_rejected(bad):
    with pytest.raises(ValueError):
        score_trials(bad, bad)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(symbol_step_s=0),
        dict(symbol_step_s=np.nan),
        dict(fft_size=64),
        dict(fft_size=True),
        dict(exact_template_energy=np.zeros(64)),
        dict(control_template_energy=np.ones(63)),
    ],
)
def test_invalid_geometry_rejected(kwargs):
    with pytest.raises(ValueError):
        score_trials(noise(22, (1, 2, 64)), noise(23, (1, 2, 64)), **kwargs)


def test_invalid_fixed_frequency_rejected():
    with pytest.raises(ValueError, match="fixed CFO"):
        score_at_frequency(np.zeros((2, 64)), np.zeros((2, 64)), np.inf)


def test_fixed_phase_kernel_direct_quadratic_and_template_energy_scaling():
    count, frequency = 128, 12_345.0
    raw, control = noise(24, (3, count)), noise(25, (3, count))
    energy = np.linspace(0.6, 2.0, count)
    fixed = score_at_frequency(raw, control, frequency, exact_template_energy=energy)
    indexes = np.arange(count)
    rotated = raw * np.exp(-2j * np.pi * frequency * indexes * 4.4e-6)
    for length in (8, 16, 32):
        kernel = np.exp(-np.abs(indexes[:, None] - indexes[None, :]) / length)
        numerator = sum(np.vdot(row, kernel @ row).real for row in rotated)
        expected = numerator / (energy.sum() * np.sum(np.abs(raw) ** 2 / energy))
        assert fixed[f"phase_kernel{length}"]["exact_score"] == pytest.approx(expected, abs=5e-14)
    original = score_bank(raw, control, exact_template_energy=energy)
    scaled = score_bank(raw, control, exact_template_energy=energy * 3)
    for method in original:
        for key in original[method]:
            assert scaled[method][key] == pytest.approx(original[method][key], abs=5e-13)
