import importlib.util
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def alignment():
    path = Path(__file__).resolve().parents[2] / "tools/compare_dsx01_graph_receivers.py"
    spec = importlib.util.spec_from_file_location("receiver_alignment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def track(rx, offset=0, slope=-1000):
    times = np.arange(0, 21, 1.0)
    return {
        "source_id": "S01",
        "receiver": rx,
        "channel": 1,
        "bank": "CH1-4",
        "rf_hz": 10e9,
        "key": f"RX{rx}",
        "times": times,
        "values": offset + slope * (times - 10),
        "observation_ids": [f"{rx}-{t}" for t in times],
        "start_s": 0.0,
        "end_s": 20.0,
        "quality_status": "no_structure_detected",
        "pieces": [
            {
                "start_s": 0.0,
                "end_s": 20.0,
                "reference_time_s": 10.0,
                "time_scale_s": 10.0,
                "coefficients_hz": [offset, slope * 10],
            }
        ],
    }


def test_alias_offset_and_receiver_correction_sign(alignment):
    a = track(1)
    b = track(2, offset=alignment.PERIOD + 49000)
    pair = alignment.pair_tracks(a, b)
    assert pair["offset_hz"] == pytest.approx(49000)
    assert pair["shape_rms_hz"] < 1e-8
    np.testing.assert_allclose(alignment.wrap(pair["delta"] - 49000), 0, atol=1e-8)


def test_no_extrapolation_or_cross_channel_matching(alignment):
    a, b = track(1), track(2)
    assert np.isnan(alignment.predict(a, np.array([-1.0, 21.0]))).all()
    b["channel"] = 2
    with pytest.raises(ValueError):
        alignment.pair_tracks(a, b)
    b["channel"] = 1
    b["start_s"] = 15
    assert alignment.pair_tracks(a, b) is None


def test_recover_common_drift_without_reusing_tracklets(alignment):
    pairs = []
    for i, mid in enumerate((30.0, 120.0, 240.0)):
        times = np.linspace(mid - 5, mid + 5, 129)
        pairs.append(
            {
                "source_id": "S01",
                "bank": "CH1-4",
                "channel": i + 1,
                "left_key": f"a{i}",
                "right_key": f"b{i}",
                "overlap_s": 10.0,
                "mid_s": mid,
                "shape_rms_hz": 20.0,
                "offset_hz": -30000 + 6 * (mid - 150),
                "both_supported": True,
                "times": times,
                "delta": -30000 + 6 * (times - 150),
            }
        )
    # A shorter duplicate must not inflate the selected calibration evidence.
    pairs.append({**pairs[0], "right_key": "duplicate", "overlap_s": 9.0})
    selected = alignment.modal_pairs(pairs)
    assert len(selected) == 3
    fit = alignment.fit_group(selected)
    assert fit["affine_at_150s_hz"] == pytest.approx(-30000)
    assert fit["affine_slope_hz_s"] == pytest.approx(6)
    assert fit["center_rms_affine_hz"] < 1e-8
    assert fit["center_rms_constant_hz"] > 400
    assert fit["calibration_supported"]


def test_temporal_controls_preserve_samples_and_shapes(alignment):
    original = [track(1), track(2, offset=49000)]
    shifted = alignment.shifted_receivers(original, shift_s=290)
    rx2 = [t for t in shifted if t["receiver"] == 2]
    assert sum(len(t["times"]) for t in rx2) == len(original[1]["times"])
    assert sorted(o for t in rx2 for o in t["observation_ids"]) == sorted(
        original[1]["observation_ids"]
    )
    for t in rx2:
        np.testing.assert_allclose(alignment.predict(t, t["times"]), t["values"], atol=1e-8)
    reversed_track = alignment.shifted_receivers(original, reverse=True)[1]
    np.testing.assert_allclose(
        alignment.predict(reversed_track, reversed_track["times"]),
        reversed_track["values"],
        atol=1e-8,
    )


def test_model_comparison_keeps_channel_groups_separate(alignment):
    pairs, fits = [], []
    for bank, offset in (("CH1-4", -9000.0), ("CH5-8", 49000.0)):
        subset = []
        for i in range(2):
            times = np.linspace(20 + 20 * i, 30 + 20 * i, 129)
            subset.append(
                {
                    "source_id": "S01",
                    "bank": bank,
                    "channel": i + 1,
                    "both_supported": True,
                    "mid_s": times.mean(),
                    "offset_hz": offset,
                    "times": times,
                    "delta": np.full(len(times), offset),
                }
            )
        fits.append(alignment.fit_group(subset))
        pairs.extend(subset)
    comparison = alignment.model_comparison(pairs, fits)
    assert comparison[0]["equal_pair_weight_curve_rms_hz"] == pytest.approx(29000)
    assert comparison[1]["pairs_curve_rms_le_450"] == 0
    assert comparison[2]["equal_pair_weight_curve_rms_hz"] == pytest.approx(0)
    assert comparison[2]["pairs_curve_rms_le_450"] == 4
    assert comparison[2]["parameters"] == 2
    assert comparison[3]["parameters"] == 2  # Sparse groups do not gain slopes.
