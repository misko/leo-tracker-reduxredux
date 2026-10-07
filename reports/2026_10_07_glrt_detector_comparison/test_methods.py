"""Numerical checks with production and independently minimized likelihood oracles."""

import numpy as np
import pytest
from methods import Whitener, fit_whitener, score_bank, score_individual_bank, score_trial_bank

from leo.analysis.starlink.pilot_methods import _glrt_pair, _SymbolCorrelations


def _noise(seed, rows):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(rows, 64)) + 1j * rng.normal(size=(rows, 64))


def _likelihood_oracle(raw, energy, covariance, *, segmented=False):
    """Optimize complex amplitudes by least squares on whitened observations.

    This computes residual likelihood gains, without implementing the prototype
    precision-weighted matched-filter formula or its FFT.
    """
    rows = len(raw)
    grid = np.fft.fftfreq(512, d=4.4e-6)
    chol = np.linalg.cholesky(covariance)
    observed = np.linalg.solve(chol, (raw / np.sqrt(energy)).T).T.reshape(-1)
    total = np.vdot(observed, observed).real
    steering = np.exp(2j * np.pi * grid[:, None] * np.arange(64) * 4.4e-6)
    steering *= np.sqrt(energy)
    segments = (slice(0, 32), slice(32, 64)) if segmented else (slice(0, 64),)
    whitened_templates = []
    for segment in segments:
        templates = np.zeros_like(steering)
        templates[:, segment] = steering[:, segment]
        whitened_templates.append(np.linalg.solve(chol, templates.T).T)
    gains = []
    for index in range(512):
        design = np.zeros((rows * 64, rows * len(segments)), dtype=complex)
        for frame in range(rows):
            for segment, templates in enumerate(whitened_templates):
                design[frame * 64 : (frame + 1) * 64, frame * len(segments) + segment] = templates[
                    index
                ]
        amplitudes = np.linalg.lstsq(design, observed, rcond=None)[0]
        residual = observed - design @ amplitudes
        gains.append((total - np.vdot(residual, residual).real) / total)
    best = int(np.argmax(gains))
    return gains[best], grid[best]


def test_current_matches_production_uniform_glrt():
    exact, control = _noise(1, 5), _noise(2, 5)
    times = np.broadcast_to(np.arange(64) * 4.4e-6, exact.shape)
    production = _glrt_pair(
        _SymbolCorrelations(exact, np.zeros_like(times), times),
        _SymbolCorrelations(control, np.zeros_like(times), times),
        size=512,
    )
    result = score_bank(exact, control)["current_glrt64_margin"]
    assert result["exact_score"] == pytest.approx(production[0][0], abs=1e-13)
    assert result["control_score"] == pytest.approx(production[1][0], abs=1e-13)
    assert result["score"] == pytest.approx(production[0][0] - production[1][0], abs=1e-13)
    assert result["cfo_hz"] == pytest.approx(production[0][1], abs=1e-7)
    assert result["control_cfo_hz"] == pytest.approx(production[1][1], abs=1e-7)


@pytest.mark.parametrize("energy", [np.ones(64), np.linspace(0.2, 3.0, 64)])
def test_identity_covariance_equivalent_to_gaussian(energy):
    training = np.sqrt(64) * np.eye(64, dtype=complex)
    whitener = fit_whitener(training)
    np.testing.assert_allclose(whitener.covariance, np.eye(64), atol=1e-14)
    results = score_bank(
        _noise(3, 3),
        _noise(4, 3),
        whitener=whitener,
        exact_template_energy=energy,
        control_template_energy=energy,
    )
    for key in ("score", "exact_score", "control_score", "cfo_hz", "control_cfo_hz"):
        assert results["adaptive_nmf64"][key] == pytest.approx(results["gaussian_glrt64"][key])


@pytest.mark.parametrize(
    "method,segmented", [("gaussian_glrt64", False), ("segmented_glrt32", True)]
)
def test_white_direct_residual_likelihood_oracle(method, segmented):
    energy = np.linspace(0.3, 2.0, 64)
    raw = _noise(9, 2)
    expected = _likelihood_oracle(raw, energy, np.eye(64), segmented=segmented)
    actual = score_bank(raw, _noise(10, 2), exact_template_energy=energy)[method]
    assert actual["score"] == pytest.approx(expected[0], abs=2e-13)
    assert actual["cfo_hz"] == expected[1]


def test_colored_direct_residual_likelihood_oracle_and_orientation():
    mixing = _noise(11, 64) / np.sqrt(64)
    covariance = mixing @ mixing.conj().T + 0.5 * np.eye(64)
    whitener = Whitener(covariance, np.linalg.solve(covariance, np.eye(64)), 0.25, 512)
    raw = _noise(12, 2)
    energy = np.linspace(0.4, 1.7, 64)
    expected = _likelihood_oracle(raw, energy, covariance)
    actual = score_bank(raw, _noise(13, 2), whitener=whitener, exact_template_energy=energy)[
        "adaptive_nmf64"
    ]
    assert actual["score"] == pytest.approx(expected[0], abs=2e-13)
    assert actual["cfo_hz"] == expected[1]
    training = _noise(14, 128) @ mixing.T
    fitted = fit_whitener(training)
    empirical = sum(np.outer(row, row.conj()) for row in training) / len(training)
    expected_covariance = 0.75 * empirical + 0.25 * np.trace(empirical).real / 64 * np.eye(64)
    np.testing.assert_allclose(fitted.covariance, expected_covariance, atol=1e-13)
    assert np.max(np.abs(fitted.covariance.imag)) > 0.1


def test_phase_and_covariance_scaling_invariance():
    training = _noise(15, 96)
    exact, control = _noise(16, 3), _noise(17, 3)
    original = score_bank(exact, control, whitener=fit_whitener(training))
    transformed = score_bank(
        exact * (3 * np.exp(0.71j)),
        control * (2 * np.exp(-0.81j)),
        whitener=fit_whitener(training * (4 * np.exp(0.3j))),
    )
    for method in original:
        for key in original[method]:
            assert transformed[method][key] == pytest.approx(original[method][key], abs=2e-12)


def test_off_grid_cfo_and_normalizer_only_changes_score():
    step = 4.4e-6
    frequency = 17.3 / (512 * step)
    exact = np.array([1 + 0.3j, 2 - 1j])[:, None] * np.exp(
        2j * np.pi * frequency * np.arange(64) * step
    )
    control = _noise(19, 2)
    result = score_bank(exact, control, whitener=fit_whitener(np.sqrt(64) * np.eye(64)))
    for method in result:
        assert result[method]["cfo_hz"] == pytest.approx(17 / (512 * step))
    assert 0.99 < result["gaussian_glrt64"]["score"] < 1.0
    random = score_bank(_noise(20, 3), control=np.resize(control, (3, 64)))
    assert random["gaussian_glrt64"]["cfo_hz"] == random["current_glrt64_margin"]["cfo_hz"]
    assert random["gaussian_glrt64"]["exact_score"] < random["current_glrt64_margin"]["exact_score"]


def test_batch_equals_single_rows_and_margin_diagnostics():
    exact, control = _noise(21, 4), _noise(22, 4)
    whitener = fit_whitener(_noise(23, 96))
    batch = score_individual_bank(exact, control, whitener=whitener)
    for index in range(4):
        single = score_bank(exact[index : index + 1], control[index : index + 1], whitener=whitener)
        for method in single:
            for key in single[method]:
                assert batch[method][key][index] == pytest.approx(single[method][key])
    for method in ("gaussian_glrt64", "adaptive_nmf64"):
        np.testing.assert_allclose(
            batch[method + "_margin"]["score"],
            batch[method]["exact_score"] - batch[method]["control_score"],
        )


@pytest.mark.parametrize("rows", [0, 2])
def test_zero_and_empty_observations_return_finite_zeros(rows):
    zeros = np.zeros((rows, 64), dtype=complex)
    result = score_bank(zeros, zeros, whitener=fit_whitener(_noise(24, 80)))
    assert all(value == 0 for method in result.values() for value in method.values())


@pytest.mark.parametrize(
    "bad", [np.zeros(64), np.zeros((2, 63)), np.full((2, 64), np.nan), np.full((2, 64), np.inf)]
)
def test_bad_observation_rejected(bad):
    with pytest.raises(ValueError):
        score_bank(bad, np.zeros((2, 64)))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(symbol_step_s=0),
        dict(symbol_step_s=np.nan),
        dict(fft_size=32),
        dict(fft_size=True),
        dict(exact_template_energy=np.zeros(64)),
    ],
)
def test_bad_geometry_rejected(kwargs):
    with pytest.raises(ValueError):
        score_bank(_noise(25, 2), _noise(26, 2), **kwargs)


@pytest.mark.parametrize(
    "training,kwargs",
    [
        (np.zeros((2, 64)), {}),
        (np.ones((1, 64)), {}),
        (np.ones((2, 64)), dict(shrinkage=0)),
        (np.ones((2, 64)), dict(shrinkage=1.1)),
    ],
)
def test_bad_training_rejected(training, kwargs):
    with pytest.raises(ValueError):
        fit_whitener(training, **kwargs)


@pytest.mark.parametrize("frames", [1, 14])
def test_pooled_trial_batch_equivalent_to_stacked_score_bank(frames):
    trials = 4
    exact = _noise(30, trials * frames).reshape(trials, frames, 64)
    control = _noise(31, trials * frames).reshape(trials, frames, 64)
    kwargs = dict(
        whitener=fit_whitener(_noise(32, 128)),
        exact_template_energy=np.linspace(0.3, 3, 64),
        control_template_energy=np.linspace(1.3, 0.4, 64),
    )
    batch = score_trial_bank(exact, control, **kwargs)
    for trial in range(trials):
        scalar = score_bank(exact[trial], control[trial], **kwargs)
        for method in scalar:
            for key in scalar[method]:
                assert batch[method][key].shape == (trials,)
                assert batch[method][key][trial] == pytest.approx(scalar[method][key], abs=2e-13)


@pytest.mark.parametrize("shape", [(3, 0, 64), (0, 14, 64), (3, 14, 64)])
def test_zero_trial_batch(shape):
    zeros = np.zeros(shape, dtype=complex)
    result = score_trial_bank(zeros, zeros, whitener=fit_whitener(_noise(33, 80)))
    for method in result.values():
        for value in method.values():
            assert value.shape == (shape[0],)
            assert np.all(value == 0)


@pytest.mark.parametrize(
    "bad", [np.zeros((3, 64)), np.zeros((3, 14, 63)), np.full((3, 14, 64), np.nan)]
)
def test_bad_trial_batch_rejected(bad):
    with pytest.raises(ValueError):
        score_trial_bank(bad, bad)
