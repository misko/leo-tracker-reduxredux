import neighbor_model
import numpy as np
from neighbor_model import fit_predict


def test_neighbor_mixture_transfers_to_unseen_symbols():
    rng = np.random.default_rng(99)
    x = rng.choice([-1.0, 1.0], size=(8, 300, 6, 5))
    coefficients = rng.normal(size=(8, 5)) + 1j * rng.normal(size=(8, 5))
    z = np.einsum("fsck,fk->fsc", x, coefficients)
    # Unknown early component must not contaminate the late-only model.
    z[:, :32] += rng.normal(size=(8, 32, 6))
    prediction, fit, ranks = fit_predict(x, z, slice(224, 256))
    assert np.allclose(fit, coefficients)
    assert np.allclose(prediction[:, 256:288], z[:, 256:288])
    assert ranks == [5] * 8


def test_rank_deficiency_is_explicit_and_prediction_remains_valid():
    rng = np.random.default_rng(89)
    p = rng.choice([-1.0, 1.0], size=(4, 300, 6))
    x = np.stack([p, p], axis=-1)
    prediction, _, ranks = fit_predict(x, p * 2, slice(224, 256))
    assert ranks == [1] * 4
    assert np.allclose(prediction, p * 2)


def test_physical_center_matches_original_prediction(monkeypatch):
    rng = np.random.default_rng(45)
    template = np.exp(0.5j * np.pi * rng.integers(0, 4, size=(1024, 301)))
    monkeypatch.setattr(
        neighbor_model, "references", lambda edge: (np.ones(1024), template, np.ones((300, 8)))
    )
    words = rng.choice([-1, 1], size=(60, 60))
    phases, bins = np.array([3, 19]), np.array([480, 487])
    physical = neighbor_model.physical_design(words, phases, bins, [(0, 0)], "upper")
    plain = neighbor_model.design(words, phases, bins, np.arange(2, 302), [(0, 0)])
    assert np.allclose(physical, plain)


def test_neighbor_pilot_keeps_its_own_phase(monkeypatch):
    template = np.ones((1024, 301), dtype=complex)
    template[487] = 1j
    monkeypatch.setattr(
        neighbor_model, "references", lambda edge: (np.ones(1024), template, np.full((300, 8), -1j))
    )
    x = neighbor_model.physical_design(
        np.ones((60, 60)), np.array([1, 2]), np.array([487]), [(0, 1)], "upper"
    )
    assert np.allclose(x, -1)
