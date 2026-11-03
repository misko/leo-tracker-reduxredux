import numpy as np
from scipy.special import expit

from cone_model import (RAD, boundary, canonical, fit, frame, logits_and_jacobian,
                        loss, probabilities, project)


def sample(n=200, seed=15):
    rng = np.random.default_rng(seed)
    unit = rng.normal(size=(n, 3))
    unit[:, 2] = abs(unit[:, 2])
    return unit/np.linalg.norm(unit, axis=1)[:, None]


def test_frames_and_separation():
    a, b = frame(270, 70), frame(90, 70)
    np.testing.assert_allclose(a@a.T, np.eye(3), atol=1e-14)
    np.testing.assert_allclose(b@b.T, np.eye(3), atol=1e-14)
    np.testing.assert_allclose(np.arccos(a[2]@b[2])/RAD, 40)


def test_boundary_exact_and_equal_shape():
    theta = np.array([45*RAD, 25*RAD, np.log(.2), 20*RAD, -40*RAD])
    for rx in [0, 1]:
        edge = boundary(theta, rx)
        logits, _ = logits_and_jacobian(theta, project(edge))
        np.testing.assert_allclose(logits[:, rx], 0, atol=1e-13)
        bore = frame(*[(270, 70), (90, 70)][rx])[2]
        angles = np.arccos(edge@bore)/RAD
        np.testing.assert_allclose([angles.min(), angles.max()], [25, 45], atol=1e-12)


def test_circular_roll_invariance_and_ellipse_canonicalization():
    p = project(sample())
    a = np.array([30*RAD, 30*RAD, np.log(.2), 0., 0.])
    b = a.copy(); b[3:] = [1.4, -.6]
    np.testing.assert_allclose(probabilities(a, p), probabilities(b, p), atol=1e-14)
    a[:2] = [20*RAD, 45*RAD]
    np.testing.assert_allclose(probabilities(a, p), probabilities(canonical(a), p), atol=1e-14)


def test_conditioning_and_gradient():
    rng = np.random.default_rng(13)
    unit = sample(); p = project(unit)
    theta = np.array([45*RAD, 25*RAD, np.log(.2), .3, -.7])
    l, _ = logits_and_jacobian(theta, p); q = expit(l)
    raw = np.column_stack((q[:, 0]*(1-q[:, 1]), q[:, 1]*(1-q[:, 0]), q[:, 0]*q[:, 1]))
    np.testing.assert_allclose(probabilities(theta, p), raw/raw.sum(axis=1)[:, None], atol=1e-12)
    outcome = rng.integers(0, 3, len(unit)); weight = rng.uniform(.1, 2, len(unit))
    _, grad = loss(theta, p, outcome, weight)
    for i in range(5):
        step = np.eye(5)[i]*1e-6
        numeric = (loss(theta+step, p, outcome, weight)[0]-loss(theta-step, p, outcome, weight)[0])/2e-6
        np.testing.assert_allclose(grad[i], numeric, rtol=1e-5, atol=1e-6)


def test_synthetic_fit_and_duplicate_invariance():
    unit = sample(1200)
    theta = np.array([45*RAD, 25*RAD, np.log(.2), .3, -.7])
    probability = probabilities(theta, project(unit))
    # Expected categorical counts, not a favorable random draw.
    u = np.repeat(unit, 3, axis=0); y = np.tile([0, 1, 2], len(unit))
    w = np.maximum(probability.ravel(), 1e-12)
    result = fit(u, y, w, starts=3)
    assert result['converged']
    assert result['in_sample_log_loss'] < result['null_log_loss']
    np.testing.assert_allclose(probabilities(result['theta'], project(unit)), probability, atol=5e-5)
    value = loss(theta, project(u), y, w)[0]
    np.testing.assert_allclose(value, loss(theta, project(np.tile(u, (2, 1))),
                                        np.tile(y, 2), np.tile(w, 2))[0])
