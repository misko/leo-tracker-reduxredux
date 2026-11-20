from types import SimpleNamespace

import numpy as np
from scipy.spatial import cKDTree

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.variants import anonymous_geometry as model


def test_polynomial_shape_has_exact_level_null_and_shares_fractional_drift():
    t = np.sort(np.r_[np.linspace(0, 15, 11), (0.5, 8.3, 13.4, 17.5)])
    x = t - t.mean()
    y = 80000.0 + 318 * x - 5.0 * x**2
    q, measured, _ = model.features(t, y)
    np.testing.assert_allclose(q @ np.ones(len(t)), 0.0, atol=1e-12)
    np.testing.assert_allclose(measured, [318.0, -10.0], atol=1e-8)
    np.testing.assert_allclose(model.features(t, y + 120_000)[1], measured, atol=1e-8)

    nuisance = SimpleNamespace(group=0, noise=np.array([30, 4]))
    spectra = [(None, None, np.array([[40.0, 0], [-140.0, -1.0]]))] * 2
    _, drift = model.clock_profile(spectra, [nuisance] * 2, False)
    np.testing.assert_array_equal(drift, [40.0, 0, 0, 0])
    loss, drift = model.clock_profile(spectra, [nuisance] * 2, True)
    np.testing.assert_array_equal(drift, np.zeros(4))
    assert loss == 0


def test_planted_held_ephemeris_is_predictable_without_reestimating_oscillator():
    point = (0, 0)
    xyz, up = geodetic_to_ecef_km(*point, 0), ecef_to_enu_matrix(*point)[2]
    t = np.linspace(1, 19, 16)
    first = np.column_stack((np.full(len(t), 6928), 7.5 * t, np.zeros(len(t))))
    other = np.column_stack((np.full(len(t), 6958), 70.0 + 7.4 * t, -1.2 * t))
    positions = np.stack((first, other))
    velocities = np.broadcast_to(np.array([[[0, 7.5, 0]], [[0, 7.4, -1.2]]]), positions.shape)
    centers = positions[:, len(t) // 2]
    tree = cKDTree(centers / np.linalg.norm(centers, axis=-1, keepdims=True))
    q = model.operator(t)
    raw = model.Profile(
        5,
        0,
        t,
        np.zeros_like(t),
        model.REFERENCE,
        q,
        np.zeros(2),
        model.FLOOR,
        positions,
        velocities,
        tree,
        0.5,
    )
    _, spectrum, _ = model.spectrum(raw, xyz, up)
    f = spectrum[0] + 13000 + 40 * (t - t.mean())
    this = model.replace(raw, f=f, features=q @ (f - f.mean()))
    drift = np.array([40.0, 0.0, 0.0, 0.0])
    held = model.check([this], point, drift, False, is_null=False)
    bad = model.check([this], point, -drift, False, is_null=False)
    assert held["held_blocks"] == 1 and held["held_loss"] < 1e-12
    assert held["conditional_held_shape_cfo_rms_hz"] < 1e-8
    assert bad["held_loss"] > 1
    old, shifted = model.shuffle([this, model.replace(this, features=np.ones(2))])
    np.testing.assert_array_equal(old.features, np.ones(2))
    np.testing.assert_array_equal(shifted.features, this.features)
    np.testing.assert_array_equal(old.f, this.f)
