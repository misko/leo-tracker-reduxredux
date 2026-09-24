import numpy as np

from tools.research.qualify_synthetic_phase_association import (
    candidate_losses,
    predictions,
    simulate_unit,
    wrap,
)


def test_wrap_is_principal():
    assert np.allclose(wrap(np.array([3 * np.pi, -3 * np.pi])), [np.pi, -np.pi], atol=1e-12)


def test_shared_receiver_phase_cancels_from_double_difference():
    rng = np.random.default_rng(4)
    source = rng.normal(size=(2, 9))
    shared = rng.normal(size=(2, 9))
    phase = np.empty((2, 2, 9))
    for r in (0, 1):
        for s in (0, 1):
            phase[r, s] = source[s] + shared[r]
    assert np.allclose(wrap((phase[1, 0] - phase[0, 0]) - (phase[1, 1] - phase[0, 1])), 0)


def test_orientation_control_changes_geometric_prediction():
    u = simulate_unit(2, "calibrated")
    truth = u["candidates"][u["label"]]
    _, nominal = predictions(truth, u["time"])
    _, rotated = predictions(truth, u["time"], np.deg2rad(169))
    assert np.max(abs(wrap(nominal - rotated))) > 0.1


def test_held_label_cannot_change_candidate_losses():
    u = simulate_unit(7, "calibrated")
    fit = {"doppler_sigma": 20.0, "phase_sigma": 0.2, "phase_enabled": True}
    before = candidate_losses(u, fit)
    u["label"] = (u["label"] + 1) % len(u["candidates"])
    after = candidate_losses(u, fit)
    assert all(np.allclose(a, b) for a, b in zip(before, after, strict=True))
