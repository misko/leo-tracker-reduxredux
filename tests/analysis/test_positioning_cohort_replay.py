"""Local cohort replay preserves random evaluation isolation and physical recovery."""

import importlib.util
from pathlib import Path

import numpy as np

from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region


def test_replay_recovers_position_without_evaluation_leakage(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "tools"))
    spec = importlib.util.spec_from_file_location(
        "cohort_replay", root / "tools/compare_positioning_cohorts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rng = np.random.default_rng(10)
    region = Region(40, -100, 5000, 5000)
    truth = np.array([42.0, -21.0])
    receiver = region.points([truth[0]], [truth[1]]).ecef_km[0]
    up = receiver / np.linalg.norm(receiver)
    t = np.linspace(-30, 30, 60)
    pp, vv = [], []
    shifted = {str(s): {"p": [], "v": []} for s in [-0.5, 0.2, 0.5]}
    for i in range(6):
        tangent = rng.normal(size=3)
        tangent -= (tangent @ up) * up
        tangent /= np.linalg.norm(tangent)
        angle = t * 7.5 / 6900 + (i - 3) * 0.025
        pp.extend(6900 * (np.cos(angle)[:, None] * up + np.sin(angle)[:, None] * tangent))
        vv.extend(7.5 * (-np.sin(angle)[:, None] * up + np.cos(angle)[:, None] * tangent))
        for shift in [-0.5, 0.2, 0.5]:
            at = angle + shift * 7.5 / 6900
            shifted[str(shift)]["p"].extend(
                6900 * (np.cos(at)[:, None] * up + np.sin(at)[:, None] * tangent)
            )
            shifted[str(shift)]["v"].extend(
                7.5 * (-np.sin(at)[:, None] * up + np.cos(at)[:, None] * tangent)
            )
    p, v = np.array(pp), np.array(vv)
    segment = np.repeat(np.arange(6), 60)
    delta = p - receiver
    y = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=1) / np.linalg.norm(delta, axis=1)
    y += segment * 10000
    train = np.tile(np.arange(60) % 5 < 3, 6)
    data = dict(y=y, p=p, v=v, segment=segment, training=train, episode=segment)
    a = module.fit(data, region, [0, 0], "observation", False)
    np.testing.assert_allclose(a["x_km"], truth, atol=1e-5)
    data["y"] = y.copy()
    data["y"][~train] += 1e6
    b = module.fit(data, region, [0, 0], "observation", False)
    np.testing.assert_allclose(a["x_km"], b["x_km"], atol=1e-8)
    assert b["evaluation_rms_hz"] > 9e5
    for shift in [-0.5, 0.5]:
        for key in ["p", "v"]:
            data[key + str(shift)] = np.array(shifted[str(shift)][key])
    shifted_delta = np.array(shifted["0.2"]["p"]) - receiver
    data["y"] = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(shifted_delta * np.array(shifted["0.2"]["v"]), axis=1)
        / np.linalg.norm(shifted_delta, axis=1)
        + segment * 10000
    )
    c = module.fit(data, region, [0, 0], "observation", False, fit_clock=True)
    np.testing.assert_allclose(c["x_km"][:2], truth, atol=0.001)
    assert abs(c["clock_s"] - 0.2) < 1e-4
    # Independent acquisition groups may have distinct UTC offsets. Neither is
    # allowed to change an orbit or refit using evaluation measurements.
    clock_groups = segment % 2
    shifted_delta = p - receiver
    nominal_y = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(shifted_delta * v, axis=1)
        / np.linalg.norm(shifted_delta, axis=1)
        + segment * 10000
    )
    data["y"][clock_groups == 0] = nominal_y[clock_groups == 0]
    grouped = module.fit(
        data, region, [0, 0], "observation", False, fit_clock=True, clock_groups=clock_groups
    )
    np.testing.assert_allclose(grouped["x_km"][:2], truth, atol=0.001)
    np.testing.assert_allclose(grouped["clock_offsets_s"], [0, 0.2], atol=1e-4)
    assert grouped["clock_s"] is None
    elevated = region.points([truth[0]], [truth[1]], 300).ecef_km[0]
    delta = np.array(shifted["0.2"]["p"]) - elevated
    data["y"] = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * np.array(shifted["0.2"]["v"]), axis=1)
        / np.linalg.norm(delta, axis=1)
        + segment * 10000
    )
    height = module.fit(data, region, [0, 0], "observation", False, fit_clock=True, fit_height=True)
    np.testing.assert_allclose(height["x_km"][:2], truth, atol=0.001)
    assert abs(height["altitude_m"] - 300) < 1
    assert abs(height["clock_s"] - 0.2) < 1e-4
