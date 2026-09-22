import importlib.util
from pathlib import Path

import numpy as np
import pytest


def module():
    path = Path(__file__).parents[2] / "reports" / "diagnose_partition_identity_changes.py"
    spec = importlib.util.spec_from_file_location("diagnose_partition_identity_changes", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_partition_masks_reproduce_chronological_and_five_block_policies():
    masks = module().partition_masks(10)
    np.testing.assert_array_equal(
        masks["chronological"],
        [True, True, True, True, True, True, False, False, False, False],
    )
    np.testing.assert_array_equal(
        masks["five_block"],
        [True, True, False, False, True, True, False, False, True, True],
    )


def test_offset_and_heldout_score_use_only_declared_training_mask():
    runner = module()
    observed = np.array([11.0, 12.0, 13.0, 20.0])
    predicted = np.array([1.0, 2.0, 3.0, 4.0])
    training = np.array([True, True, True, False])
    result = runner.fitted_residuals(observed, predicted, training)
    assert result["offset_hz"] == pytest.approx(10.0)
    assert result["training_rms_hz"] == pytest.approx(0.0)
    assert result["heldout_rms_hz"] == pytest.approx(6.0)
    poisoned = observed.copy()
    poisoned[-1] = 1e9
    changed = runner.fitted_residuals(poisoned, predicted, training)
    assert changed["offset_hz"] == result["offset_hz"]
    assert changed["training_rms_hz"] == result["training_rms_hz"]
    assert changed["heldout_rms_hz"] > 1e8


def test_strong_changes_uses_first_comparison_and_requires_four_rows():
    runner = module()
    changes = [
        {
            "left_norad": index + 1,
            "right_norad": index + 11,
            "left_weight": 0.9,
            "right_weight": 0.95,
        }
        for index in range(4)
    ]
    document = {
        "schema": "joint-partition-association-comparison-v1",
        "comparisons": [
            {
                "left": "chronological-set",
                "right": "blocked-sac-set",
                "changed_candidate_leaders": changes
                + [
                    {
                        "left_norad": 100,
                        "right_norad": 200,
                        "left_weight": 0.89,
                        "right_weight": 1.0,
                    }
                ],
            }
        ],
    }
    assert runner.strong_changes(document) == changes
    document["comparisons"][0]["changed_candidate_leaders"].pop(0)
    with pytest.raises(ValueError, match="exactly four"):
        runner.strong_changes(document)


def test_common_time_shape_uses_overlap_without_extrapolation():
    runner = module()
    result = runner.common_time_shape(
        np.array([0.0, 1.0, 2.0, 3.0]),
        np.array([10.0, 11.0, 12.0, 13.0]),
        np.array([1.0, 2.0, 3.0, 4.0]),
        np.array([-4.0, -2.0, 0.0, 2.0]),
        points=9,
    )
    assert result["common_start_s"] == 1.0
    assert result["common_stop_s"] == 3.0
    assert result["correlation"] == pytest.approx(1.0)
    assert result["normalized_rms_difference"] == pytest.approx(0.0, abs=1e-12)
