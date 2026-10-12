from pathlib import Path

import numpy as np
import pytest

from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence, SparseConfig, fit_sparse
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.check_sparse_glrt_minimum import local_curvature
from tools.evaluate_sparse_glrt import coordinates, local_output, nuisance_seeds, prediction
from tools.summarize_sparse_glrt import diagnostics


def test_local_coordinates_preserve_meter_scale_and_doppler_sign():
    site = dict(latitude_deg=37.858988, longitude_deg=-122.478103, altitude_m=-29.0)
    receiver = geodetic_to_ecef_km(**site)
    lat, lon = coordinates(site, 1000, 0)
    displaced = geodetic_to_ecef_km(lat, lon, site["altitude_m"])
    assert np.linalg.norm(displaced - receiver) * 1000 == pytest.approx(1000, abs=0.02)
    up = ecef_to_enu_matrix(site["latitude_deg"], site["longitude_deg"])[2]
    # An overhead receding source must produce a negative received-minus-TX CFO.
    p = np.tile(receiver + 550 * up, (1, 3, 1))
    v = np.tile(up, (1, 3, 1))
    data = FrequencyEvidence(
        ("a", "b", "c"),
        np.zeros((3, 1)),
        np.ones((3, 1)),
        np.ones(3),
        np.zeros(3, dtype=int),
        np.arange(3.0),
    )
    bank = dict(
        position=p,
        velocity=v,
        inverse=np.arange(3),
        rf_hz=np.full(3, 11e9),
        nominal_correction_hz=np.full(3, 125.0),
    )
    predicted, visible = prediction(bank, data, site, (0, 0))
    np.testing.assert_allclose(predicted, -11e9 / 299792.458 + 125, atol=1e-6)
    assert visible.all()


def test_horizon_and_receiver_rotation_use_the_same_frame():
    site = dict(latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0)
    data = FrequencyEvidence(
        ("a", "b", "c"),
        np.zeros((3, 1)),
        np.ones((3, 1)),
        np.ones(3),
        np.zeros(3, dtype=int),
        np.arange(3.0),
    )
    bank = dict(
        position=np.tile([-6900.0, 0, 0], (1, 3, 1)),
        velocity=np.zeros((1, 3, 3)),
        inverse=np.arange(3),
        rf_hz=np.full(3, 11e9),
        nominal_correction_hz=np.zeros(3),
    )
    _, visible = prediction(bank, data, site, (0, 0))
    assert not visible.any()


def test_replay_cannot_publish_beneath_qnap():
    with pytest.raises(ValueError, match="QNAP"):
        local_output(Path("/mnt/qnap01/new-analysis"))


def test_frequency_diagnostics_match_signal_mass_and_exact_residual():
    n = 30
    predicted = np.linspace(-10000, 10000, n)[:, None]
    data = FrequencyEvidence(
        tuple(map(str, range(n))),
        predicted.copy(),
        np.ones((n, 1)),
        np.full(n, 0.95),
        np.zeros(n, dtype=int),
        np.arange(float(n)),
    )
    config = SparseConfig(scale_hz=100.0, maximum_satellites=1)
    fit = fit_sparse(data, predicted, np.ones_like(predicted, bool), [[0]], config)
    summary = diagnostics(data, predicted, np.ones_like(predicted, bool), fit, config, [(0, 0)])
    assert summary["total_signal_support"] == pytest.approx(sum(fit["signal_support"]))
    assert summary["median_absolute_residual_hz"] == pytest.approx(0, abs=0.01)


def test_offset_starts_include_cross_band_alignment_without_constraining_fit():
    data = FrequencyEvidence(
        ("a", "b", "c", "d"),
        np.array([[100000.0], [-100000.0], [200000.0], [-200000.0]]),
        np.ones((4, 1)),
        np.ones(4),
        np.arange(4),
        np.arange(4.0),
    )
    seeds = nuisance_seeds(data, np.zeros((4, 1)), np.ones((4, 1), bool), count=1)
    assert seeds[0][0] != seeds[0][1]
    assert any(s[0] == s[1] == seeds[0][0] and s[2] == s[3] == seeds[0][2] for s in seeds)
    assert any(s[0] == s[1] == seeds[0][1] and s[2] == s[3] == seeds[0][3] for s in seeds)


def test_local_minimum_stencil_recovers_cross_curvature():
    h = np.array([[3.0, -0.5], [-0.5, 2.0]])
    g = np.array([0.2, -0.3])
    step = 0.25
    loss = {}
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            x = step * np.array([i, j])
            loss[i, j] = float(10 + g @ x + 0.5 * x @ h @ x)
    actual_g, actual_h = local_curvature(loss, step)
    np.testing.assert_allclose(actual_g, g, atol=1e-12)
    np.testing.assert_allclose(actual_h, h, atol=1e-12)
