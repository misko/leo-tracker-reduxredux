import importlib.util
from pathlib import Path

import numpy as np
import pytest
from numpy.polynomial import legendre as leg


@pytest.fixture
def model(monkeypatch):
    folder = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "dsx_receiver_model", folder / "model_dsx01_receiver_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calibration_cores(common_slope=0.0):
    cores = []
    for band, offset, drift in (("CH1-4", -9000.0, -6.0), ("CH5-8", 49000.0, 4.0)):
        for i, mid in enumerate((30.0, 130.0, 250.0)):
            t1 = np.linspace(mid - 10, mid + 10, 31)
            t2 = t1 + 0.03
            t = np.r_[t1, t2]
            rx = np.r_[np.ones(len(t1), int), np.full(len(t2), 2)]
            y = 10000 - 1500 * (t - mid) + 2 * (t - mid) ** 2 + common_slope * (t - 150)
            y += (rx == 2) * (offset + drift * (t - 150))
            cores.append(
                {
                    "source_id": "S01",
                    "bank": band,
                    "channel": i + 1,
                    "left_key": f"a-{band}-{i}",
                    "right_key": f"b-{band}-{i}",
                    "t": t,
                    "y": y,
                    "rx": rx,
                    "x": (t - mid) / 10,
                    "mid_s": mid,
                    "offset_hz": offset + drift * (mid - 150),
                }
            )
    return cores


def test_joint_fit_recovers_relative_band_offsets_and_drifts(model):
    fit = model.fit_calibration(calibration_cores(), "band_drift")
    assert fit["data_normal_rank"] == 4
    for group, offset, drift in zip(fit["groups"], (-9000, 49000), (-6, 4), strict=True):
        assert group["offset_at_150s_hz"] == pytest.approx(offset, abs=0.1)
        assert group["relative_drift_hz_s"] == pytest.approx(drift, abs=0.02)
        assert group["strong_calibration"]
    constant = model.fit_calibration(calibration_cores(), "constant")
    assert fit["penalized_score"] < constant["penalized_score"]


def test_common_hardware_drift_is_a_polynomial_gauge(model):
    a = model.fit_calibration(calibration_cores(), "band_drift")
    b = model.fit_calibration(calibration_cores(common_slope=123.0), "band_drift")
    for ga, gb in zip(a["groups"], b["groups"], strict=True):
        assert ga["offset_at_150s_hz"] == pytest.approx(gb["offset_at_150s_hz"], abs=1e-5)
        assert ga["relative_drift_hz_s"] == pytest.approx(gb["relative_drift_hz_s"], abs=1e-7)


def synthetic_track(rx, start, end, *, extra_offset=0.0):
    t = np.arange(start, end + 0.1, 0.5)
    rng = np.random.default_rng(100 + rx)
    y = 10000 - 1000 * t + 0.4 * t**2 + rng.normal(0, 35, len(t))
    if rx == 2:
        y += 30000 + 3 * (t - 150) + extra_offset
    ref, scale = (start + end) / 2, (end - start) / 2
    coeff = leg.legfit((t - ref) / scale, y, 2)
    return {
        "key": f"RX{rx}",
        "receiver": rx,
        "bank": "CH1-4",
        "source_id": "S01",
        "channel": 1,
        "times": t,
        "values": y,
        "start_s": start,
        "end_s": end,
        "observation_ids": [f"RX{rx}-{i}" for i in range(len(t))],
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


def calibration():
    return {
        ("S01", "CH1-4"): {
            "offset_at_150s_hz": 30000,
            "relative_drift_hz_s": 3.0,
            "strong_calibration": True,
        }
    }


def test_sequential_handoff_preserves_original_points_and_has_no_jump(model):
    tracks = [synthetic_track(1, 0.0, 30.0), synthetic_track(2, 32.0, 62.0)]
    result = model.stitch(tracks, calibration())
    assert result["output_tracks"] == 1
    assert result["accepted_edges"][0]["kind"] == "sequential"
    assert result["accepted_edges"][0]["gap_s"] == 2.0
    assert result["associated_points"] == 122
    group = result["merged_groups"][0]
    assert group["fully_supported"]
    assert group["max_absolute_residual_hz"] < 150
    assert set(group["members"]) == {"RX1", "RX2"}
    assert not any(d["flags"] for d in group["diagnostics"].values())
    # One polynomial spans both receivers; its value and slope are unique at the handoff.
    assert group["degree"] <= 4


def test_wrong_shift_or_long_gap_does_not_create_a_handoff(model):
    wrong = [synthetic_track(1, 0.0, 30.0), synthetic_track(2, 32.0, 62.0, extra_offset=20000)]
    assert model.stitch(wrong, calibration())["output_tracks"] == 2
    gap = [synthetic_track(1, 0.0, 30.0), synthetic_track(2, 45.0, 75.0)]
    assert model.stitch(gap, calibration())["output_tracks"] == 2


def test_receiver_specific_trend_cannot_cancel_in_joint_diagnostics(model):
    t = np.linspace(0, 40, 100)
    residual = 10 * (t - 20)
    diagnostic = model.noise_diagnostic(t, residual)
    assert diagnostic["linear_component_z"] > 3.5
    assert "linear_residual_component" in diagnostic["flags"]


def test_sparse_anchor_does_not_authorize_scan_wide_stitching(model):
    fit = model.fit_calibration(calibration_cores()[:1], "band_drift")
    assert not fit["groups"][0]["strong_calibration"]
    cal = calibration()
    cal["S01", "CH1-4"]["strong_calibration"] = False
    tracks = [synthetic_track(1, 0.0, 30.0), synthetic_track(2, 32.0, 62.0)]
    assert model.stitch(tracks, cal)["output_tracks"] == 2
