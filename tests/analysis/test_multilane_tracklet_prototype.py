import importlib.util
from pathlib import Path

import numpy as np
import pytest
from numpy.polynomial import legendre as leg


@pytest.fixture
def prototype(monkeypatch):
    folder = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "multilane_prototype", folder / "prototype_multilane_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def beta():
    return np.array(
        [12000.0, -18000.0, 3000.0, 31000.0, 2 * 150.0, -3 * 150.0, -4 * 150.0, 5 * 150.0]
    )


def track(prototype, rx, ch, start=0.0, end=30.0, alias=0, source="synthetic"):
    t = np.arange(start, end + 0.1, 0.5)
    rf = (10.7096875 + 0.25 * (ch - 1)) * 1e9
    q = rf / prototype.REFERENCE_RF
    g = 2 * (rx - 1) + int(ch > 4)
    p = 80000 - 1800 * (t - 15) + 0.6 * (t - 15) ** 2
    rng = np.random.default_rng(50 + 17 * rx + ch)
    y = q * p + beta()[g] + beta()[g + 4] * (t - 150) / 150
    y += rng.normal(0, 35, len(t)) - alias * prototype.PERIOD
    ref, scale = (start + end) / 2, (end - start) / 2
    coeff = leg.legfit((t - ref) / scale, y, 2)
    key = f"{source}-RX{rx}-CH{ch}"
    return {
        "key": key,
        "receiver": rx,
        "channel": ch,
        "bank": "CH1-4" if ch <= 4 else "CH5-8",
        "source_id": source,
        "rf_hz": rf,
        "times": t,
        "values": y,
        "start_s": start,
        "end_s": end,
        "quality_status": "no_structure_detected",
        "observation_ids": [f"{key}-{i}" for i in range(len(t))],
        "pieces": [
            {
                "start_s": start,
                "end_s": end,
                "reference_time_s": ref,
                "time_scale_s": scale,
                "coefficients_hz": coeff,
                "degree": 2,
                "indices": list(range(len(t))),
            }
        ],
    }


@pytest.mark.parametrize("rx,ch", [(1, 2), (1, 7), (2, 1), (2, 3), (2, 8)])
@pytest.mark.parametrize("sequential", [False, True])
def test_any_receiver_channel_pair_can_share_a_curve(prototype, rx, ch, sequential):
    a = track(prototype, 1, 1)
    b = track(
        prototype,
        rx,
        ch,
        start=32.0 if sequential else 0.0,
        end=62.0 if sequential else 30.0,
        alias=1,
    )
    mapping = {t["key"]: t for t in (a, b)}
    fit, reason = prototype.fit_union({a["key"]: 0, b["key"]: 1}, mapping, beta(), True)
    assert reason == "accepted"
    assert fit["fully_supported"]
    assert fit["points"] == 122
    assert fit["max_residual_hz"] < 200
    assert fit["degree"] <= 4


def test_rf_scaling_is_needed_for_widely_separated_channels(prototype):
    a, b = track(prototype, 1, 1), track(prototype, 1, 8)
    mapping = {t["key"]: t for t in (a, b)}
    fit, reason = prototype.fit_union({a["key"]: 0, b["key"]: 0}, mapping, beta(), False)
    assert fit is None and reason == "point_gate"
    fit, _ = prototype.fit_union({a["key"]: 0, b["key"]: 0}, mapping, beta(), True)
    assert fit is not None


def test_cross_scan_and_large_gap_are_rejected(prototype):
    a, b = track(prototype, 1, 1), track(prototype, 2, 8, source="other")
    with pytest.raises(ValueError):
        prototype.fit_union({a["key"]: 0, b["key"]: 0}, {a["key"]: a, b["key"]: b}, beta(), True)
    b = track(prototype, 2, 8, start=45.0, end=75.0)
    fit, reason = prototype.fit_union(
        {a["key"]: 0, b["key"]: 0}, {a["key"]: a, b["key"]: b}, beta(), True
    )
    assert fit is None and reason == "gap_or_duplicate"


def test_alias_lifts_are_applied_before_rf_normalization(prototype):
    a = track(prototype, 1, 1)
    b = track(prototype, 2, 8, alias=1)
    arrays = prototype.observation_arrays(
        {a["key"]: 0, b["key"]: 1}, {a["key"]: a, b["key"]: b}, beta(), True
    )
    mask = arrays["ch"] == 8
    expected = b["values"] + prototype.PERIOD - prototype.nuisance(b, b["times"], beta())
    np.testing.assert_allclose(arrays["y"][mask], expected, atol=1e-8)
    assert prototype.PERIOD / prototype.ratio(a, True) != pytest.approx(
        prototype.PERIOD / prototype.ratio(b, True)
    )


def test_disconnected_calibration_frames_are_not_joined(prototype):
    a, b = track(prototype, 1, 1), track(prototype, 2, 8)
    cal = {"beta": beta().tolist(), "groups": [{"group": i, "frame": i} for i in range(4)]}
    assert prototype.candidate_edges([a, b], cal, True) == []


def test_independent_lane_time_control_preserves_every_measurement(prototype, monkeypatch):
    folder = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "multilane_validation", folder / "validate_multilane_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    originals = [
        track(prototype, 1, 1, start=90.0, end=160.0),
        track(prototype, 2, 8, start=220.0, end=290.0),
    ]
    shifted = module.shift_lanes(originals, seed=41)
    assert sorted(oid for t in shifted for oid in t["observation_ids"]) == sorted(
        oid for t in originals for oid in t["observation_ids"]
    )
    assert all(np.all((t["times"] >= 0) & (t["times"] < 300)) for t in shifted)
    assert len({t["key"] for t in shifted}) == len(shifted)
