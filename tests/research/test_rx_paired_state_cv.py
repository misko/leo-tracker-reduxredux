import copy
import math

import numpy as np
import pytest

from tools.rx_paired_state_cv import controlled, prepare_fold, raw_lane


def document():
    lanes = []
    for record in range(6):
        windows = []
        for i in range(4):
            windows.append(
                {
                    "source_window_id": f"{record}-{i}",
                    "prediction_utc_ns": 1000000000 * (i + 1),
                    "role": "reception" if i < 2 else "held_frequency",
                    "observed": {"rx0": [{}] if i % 2 else [], "rx1": [{}]},
                    "predictions": [
                        {
                            "track_id": "a",
                            "catalog_number": 1,
                            "los_enu_unit": {"east": i * 0.1, "up": 0.5 + i * 0.05},
                            "visible": True,
                        }
                    ],
                }
            )
        lanes.append(
            {
                "lane": {"session_id": f"s{record}"},
                "recording_split": "calibration",
                "sample_rate_hz": 5000000,
                "windows": windows,
                "components": [
                    {
                        "kind": "track_candidate",
                        "track_id": "a",
                        "catalog_number": 1,
                        "log_prior": math.log(0.7),
                    },
                    {"kind": "other", "log_prior": math.log(0.3)},
                ],
            }
        )
    return {"schema": "rx-geometry-dataset/v1", "lanes": lanes}


def test_training_is_physically_isolated_and_reception_center_carries_forward():
    doc = document()
    training, held, receipt = prepare_fold(doc, 0)
    changed = copy.deepcopy(doc)
    for lane in changed["lanes"]:
        for w in lane["windows"]:
            if lane["lane"]["session_id"] == "s0" or w["role"] == "held_frequency":
                w["observed"] = {"rx0": [], "rx1": []}
                w["predictions"][0]["los_enu_unit"]["east"] += 0.01
    other_training, _, other = prepare_fold(changed, 0)
    for key in ("background", "geometry_scales", "training_category_counts"):
        assert receipt[key] == other[key]
    for a, b in zip(training, other_training, strict=True):
        np.testing.assert_array_equal(a["geometry"], b["geometry"])
        assert set(a["roles"]) == {"reception"}
    np.testing.assert_allclose(held[0]["geometry"][:2].mean(axis=0), 0, atol=1e-14)
    assert held[0]["geometry"][2, 0, 2] > 0
    assert np.exp(held[0]["prior"][-1]) == pytest.approx(0.3)


def test_frequency_margin_and_duplicate_entries_do_not_change_outcomes():
    original = document()["lanes"][0]
    changed = copy.deepcopy(original)
    for w in changed["windows"]:
        for r in ("rx0", "rx1"):
            w["observed"][r] = [{"canonical_rx0_hz": 1e99, "fractional_margin": -99}] * (
                4 if w["observed"][r] else 0
            )
    a, b = raw_lane(original), raw_lane(changed)
    for key in ("y", "geometry", "prior", "nuisance"):
        np.testing.assert_array_equal(a[key], b[key])
    del changed["windows"][0]["observed"]["rx0"]
    with pytest.raises(ValueError, match="receiver"):
        raw_lane(changed)


def test_controls_preserve_unsigned_features_and_observations():
    _, held, _ = prepare_fold(document(), 0)
    for name in ("O_swap", "O_reverse", "O_permute"):
        changed = controlled(held, name)[0]
        np.testing.assert_array_equal(changed["geometry"][..., :2], held[0]["geometry"][..., :2])
        np.testing.assert_array_equal(changed["y"], held[0]["y"])
    swapped = controlled(held, "O_swap")[0]
    np.testing.assert_array_equal(swapped["geometry"][..., 2], -held[0]["geometry"][..., 2])
