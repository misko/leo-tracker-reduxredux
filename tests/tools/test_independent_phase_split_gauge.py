import copy

import pytest

from tools.research.independent_phase_split_gauge import (
    FOLD_PERIOD_HZ,
    calibration_gauge,
    odd_response,
)


def example():
    return {
        "observation": {
            "visit_index": 1,
            "time_s": 2.0,
            "dealiased_native_cfo_hz": 100.0,
            "rf_normalization_scale": 0.9,
        },
        "selected_seed_index": 0,
        "branches": [
            {
                "frames": [
                    {
                        "group_id": 0,
                        "session_time_s": 2.01,
                        "frame": {
                            "training_supported": True,
                            "even": {
                                "absolute_cfo_hz": 90 - FOLD_PERIOD_HZ,
                                "search_boundary": False,
                            },
                            "odd": None,
                        },
                    },
                    {
                        "group_id": 1,
                        "session_time_s": 2.03,
                        "frame": {
                            "training_supported": True,
                            "even": None,
                            "odd": {
                                "absolute_cfo_hz": 80 - FOLD_PERIOD_HZ,
                                "search_boundary": True,
                            },
                        },
                    },
                ]
            }
        ],
    }


def test_half_period_correction_preserves_residual_and_boundary_response():
    row = example()
    gauge = calibration_gauge(row)
    assert gauge["alias_lift_index"] == 1
    assert gauge["native_closure_hz"] == pytest.approx(-10)
    response = odd_response(row)
    assert response["observed_hz"] == pytest.approx([72])
    assert response["odd_search_boundary_count"] == response["frame_count"] == 1


def test_odd_mutation_cannot_select_another_lattice_integer():
    row = example()
    changed = copy.deepcopy(row)
    changed["branches"][0]["frames"][1]["frame"]["odd"]["absolute_cfo_hz"] += 9 * FOLD_PERIOD_HZ
    assert calibration_gauge(changed) == calibration_gauge(row)
    assert odd_response(changed)["observed_hz"][0] - odd_response(row)["observed_hz"][
        0
    ] == pytest.approx(9 * FOLD_PERIOD_HZ * 0.9)


def test_missing_calibration_is_an_explicit_dwell_abstention():
    row = example()
    row["branches"][0]["frames"][0]["frame"]["training_supported"] = False
    response = odd_response(row)
    assert response["frame_count"] == 0
    assert response["abstention_reason"] == "no_calibration_even_support"


def test_coarse_gauge_does_not_replace_pilot_with_archived_glrt():
    row = example()
    changed = copy.deepcopy(row)
    changed["observation"]["dealiased_native_cfo_hz"] += 1000
    assert odd_response(changed)["observed_hz"] == odd_response(row)["observed_hz"]
