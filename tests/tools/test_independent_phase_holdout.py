import copy

import numpy as np

from tools.research.evaluate_independent_phase_holdout import (
    NATIVE_ALIAS_HZ,
    held_rows,
    odd_response,
    score_responses,
)


def test_held_scope_is_exact_complement_of_frozen_training():
    binding = {
        "observations": [{"visit_index": i} for i in range(27)],
        "fresh_random_whole_visit_split": [
            {"visit_index": i, "partition": "held" if i < 12 else "train"} for i in range(27)
        ],
    }
    assert [row["visit_index"] for row in held_rows(binding)] == list(range(12))


def test_odd_cfo_never_changes_alias_and_boundary_response_is_retained():
    row = {
        "observation": {
            "visit_index": 7,
            "time_s": 3.0,
            "dealiased_native_cfo_hz": 10 + NATIVE_ALIAS_HZ,
            "rf_normalization_scale": 0.9,
        },
        "selected_seed_index": 0,
        "branches": [
            {
                "seed_cfo_hz": 10,
                "frames": [
                    {
                        "group_id": 1,
                        "session_time_s": 3.0,
                        "frame": {
                            "training_supported": True,
                            "odd": {"absolute_cfo_hz": 11, "search_boundary": True},
                        },
                    }
                ],
            }
        ],
    }
    first = odd_response(row)
    changed = copy.deepcopy(row)
    changed["branches"][0]["frames"][0]["frame"]["odd"]["absolute_cfo_hz"] += NATIVE_ALIAS_HZ
    second = odd_response(changed)
    assert first["alias_lift_index"] == second["alias_lift_index"] == 1
    assert first["odd_search_boundary_count"] == first["frame_count"] == 1
    np.testing.assert_allclose(
        second["observed_hz"][0] - first["observed_hz"][0], 0.9 * NATIVE_ALIAS_HZ
    )


def test_whole_visit_weighting_and_abstentions_are_explicit():
    responses = [
        {"visit_index": 1, "observed_hz": [3]},
        {"visit_index": 2, "observed_hz": [4] * 20},
        {"visit_index": 3, "observed_hz": []},
    ]
    models = {"same": [[0], [0] * 20, []]}
    result = score_responses(responses, models)["same"]
    assert result["total_held_visits"] == 3
    assert result["covered_held_visits"] == 2
    assert not result["all_held_covered"]
    assert result["conditional_equal_visit_rms_hz"] == np.sqrt(12.5)
