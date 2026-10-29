"""The shared-phase normal solve agrees with an independent dense point fit."""

import importlib
from pathlib import Path

import numpy as np

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.shared_orbit_phase_fit import (
    BIAS_SIGMA_HZ,
    NOISE_HZ,
    apply_phases,
    augment_phase_statistics,
    box_quadratic,
    joint_update,
    profile_phases,
    recenter_phases,
)


def fixture(monkeypatch, linear=False):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    matching = importlib.import_module("analyze_dsx01_fixed_site")
    times = np.arange(0, 301, 3.0)
    frequency = np.stack(
        [50000 - 1500 * times + 0.5 * times**2, 40000 - 1200 * times + 0.3 * times**2]
    )
    derivative = np.stack([3000 + 0.02 * (times - 150) ** 2, 1200 + 2 * times])
    beta = np.array([100.0, 0, -200, 0, 30, 0, -15, 0])
    groups = []
    for ci in range(2):
        members = []
        t = times[times <= 120] if ci == 0 else times[times >= 180]
        indexes = np.searchsorted(times, t)
        for g in (0, 2):
            rf = (10.94 + ci * 0.25) * 1e9
            q = rf / 11.5e9
            y = (
                q * frequency[0, indexes]
                + beta[g]
                + beta[g + 4] * (t - 150) / 150
                + q * derivative[0, indexes] * 0.4
                + (-200 if ci == 0 else 200)
            )
            members.append(
                dict(
                    key=f"{ci}-{g}",
                    receiver=g // 2 + 1,
                    channel=ci + 1,
                    rf_hz=rf,
                    times=t,
                    values=y,
                )
            )
        groups.append((str(ci), members))
    if linear:
        groups.append(
            (
                "linear",
                [
                    dict(
                        key="linear",
                        receiver=1,
                        channel=1,
                        rf_hz=11.5e9,
                        times=times,
                        values=90000 + 900 * times,
                    )
                ],
            )
        )
    stats = matching.statistics(
        groups,
        dict(time_s=times, doppler_0=frequency, elevation_deg=np.full(frequency.shape, 45.0)),
        {"1": 0, "2": 0},
    )
    return (
        augment_phase_statistics(stats, times, frequency, derivative),
        times,
        frequency,
        derivative,
    )


def test_schur_solve_matches_dense_gaussian_points(monkeypatch):
    stats, times, frequency, derivative = fixture(monkeypatch)
    best = np.zeros(2, int)
    beta, phase, info = joint_update(
        stats,
        best,
        np.zeros_like(stats["mean"]),
        np.zeros(8),
        np.zeros(2),
        np.array([1.2, 1.2]),
        np.full(2, 15.0),
        np.ones(2, bool),
    )
    rows, values = [], []
    for fi, t in enumerate(stats["fragments"]):
        ci, g = stats["ci"][fi], stats["g"][fi]
        indexes = np.searchsorted(times, t["times"])
        a = np.zeros((len(indexes), 11))
        a[:, g], a[:, g + 4] = 1, (t["times"] - 150) / 150
        a[:, 8] = stats["q"][fi] * derivative[0, indexes]
        a[:, 9 + ci] = 1
        w = np.sqrt(min(1.0, 50 / stats["count"][ci]))
        rows.extend(w * a)
        values.extend(w * (t["values"] - stats["q"][fi] * frequency[0, indexes]))
    for g in range(4):
        a = np.zeros(11)
        a[g + 4] = NOISE_HZ / (150 * 2)
        rows.append(a)
        values.append(0)
    for ci in range(2):
        a = np.zeros(11)
        a[9 + ci] = np.sqrt(min(1.0, 50 / stats["count"][ci])) * NOISE_HZ / BIAS_SIGMA_HZ
        rows.append(a)
        values.append(0)
    a = np.zeros(11)
    a[8] = NOISE_HZ / 1.2
    rows.append(a)
    values.append(0)
    expected = np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)[0]
    np.testing.assert_allclose(beta, expected[:8], atol=1e-4)
    np.testing.assert_allclose(phase, [expected[8], 0], atol=1e-6)
    assert info["phase_parameters"] == 1  # Both components share one satellite.
    assert info["box_solver_converged"]


def test_linear_fragment_cannot_calibrate_and_absent_groups_are_zero(monkeypatch):
    a, *_ = fixture(monkeypatch)
    b, *_ = fixture(monkeypatch, linear=True)
    arguments = dict(
        beta=np.array([0, 8000.0, 0, 9000.0, 0, 600.0, 0, 700.0]),
        phases=np.zeros(2),
        sigma_s=np.ones(2),
        bounds_s=np.full(2, 15.0),
    )
    x = joint_update(
        a, np.zeros(2, int), np.zeros_like(a["mean"]), selected=np.ones(2, bool), **arguments
    )
    y = joint_update(
        b, np.zeros(3, int), np.zeros_like(b["mean"]), selected=np.ones(3, bool), **arguments
    )
    np.testing.assert_allclose(x[0], y[0], atol=1e-6)
    np.testing.assert_allclose(x[1], y[1], atol=1e-6)
    assert x[0][[1, 3, 5, 7]].tolist() == [0.0, 0.0, 0.0, 0.0]


def test_zero_phase_nests_existing_profile_and_recentring_is_exact(monkeypatch):
    stats, *_ = fixture(monkeypatch)
    beta = np.arange(8.0)
    a = profile_phases(stats, beta, np.zeros(2))
    b = profile_component_bias(stats, beta, bias_sigma_hz=1000)
    np.testing.assert_allclose(a.score, b.score)
    anchor = np.array([0.3, -0.4])
    virtual = recenter_phases(apply_phases(stats, anchor), anchor)
    # Recentring expects the cross-data statistic at the tangent's origin.
    tangent = apply_phases(stats, anchor)
    tangent["zh"] = stats["zh"] - stats["hh"] * anchor
    virtual = recenter_phases(tangent, anchor)
    for name in ("mean", "xz", "rss", "zh"):
        np.testing.assert_allclose(virtual[name], stats[name], rtol=1e-9, atol=1e-4)


def test_box_solver_releases_a_bound_when_another_coordinate_moves():
    normal = np.array([[2.0, -1.0], [-1.0, 2.0]])
    rhs = np.array([-1.0, 3.0])
    answer, converged = box_quadratic(normal, rhs, np.zeros(2), np.full(2, 2.0))
    np.testing.assert_allclose(answer, [1 / 3, 5 / 3], atol=1e-9)
    assert converged
    answer, converged = box_quadratic(normal, np.array([10.0, 3.0]), np.zeros(2), np.ones(2))
    np.testing.assert_allclose(answer, [1.0, 1.0], atol=1e-9)
    assert converged


def test_four_receiver_band_offsets_and_small_drifts_are_independent(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    matching = importlib.import_module("analyze_dsx01_fixed_site")
    times = np.arange(301.0)
    frequency = (70000 - 1500 * times + times**2)[None, :]
    offsets = np.array([500.0, -3500.0, 1700.0, 9200.0])
    drift = np.array([0.2, -0.7, 0.8, -0.3])
    groups = []
    for g in range(4):
        groups.append(
            (
                str(g),
                [
                    dict(
                        key=str(g),
                        receiver=g // 2 + 1,
                        channel=1 + 4 * (g % 2),
                        rf_hz=11.5e9,
                        times=times,
                        values=frequency[0] + offsets[g] + drift[g] * (times - 150),
                    )
                ],
            )
        )
    stats = matching.statistics(
        groups,
        dict(time_s=times, doppler_0=frequency, elevation_deg=np.full(frequency.shape, 45.0)),
        {"1": 0, "5": 0},
    )
    stats = augment_phase_statistics(stats, times, frequency, np.zeros_like(frequency))
    beta, _, info = joint_update(
        stats,
        np.zeros(4, int),
        np.zeros_like(stats["mean"]),
        np.zeros(8),
        np.zeros(1),
        np.zeros(1),
        np.zeros(1),
        np.ones(4, bool),
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1.0,
    )
    np.testing.assert_allclose(beta[:4], offsets, atol=1e-5)
    # Declared Gaussian prior shrinks slopes by a known common factor.
    weight = 50 / len(times)
    information = weight * np.sum(((times - 150) / 150) ** 2)
    shrinkage = information / (information + NOISE_HZ**2 / 75**2)
    np.testing.assert_allclose(beta[4:8] / 150, drift * shrinkage, atol=1e-7)
    assert info["supported_groups"] == [True] * 4
    # An RX-by-band interaction is allowed; additive RX+band offsets would fail.
    assert abs((beta[3] - beta[1]) - (beta[2] - beta[0])) > 1000
