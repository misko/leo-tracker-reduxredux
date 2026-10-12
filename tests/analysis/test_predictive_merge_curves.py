from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.continuous_track_merge import TrackSeries
from leo.analysis.predictive_merge_curves import (
    PredictiveCurveConfiguration,
    compare_predictive_curves,
)


def pair(step=0):
    groups = []
    rng = np.random.default_rng(881)
    for index, times in enumerate((np.arange(0, 24, 0.2), np.arange(25.4, 50, 0.2))):
        values = 100000 - 2000 * times + 15 * times**2 + 0.03 * times**3
        values += rng.normal(0, 20, len(times)) + index * step
        ids = tuple(f"{index}:{i}" for i in range(len(times)))
        groups.append(
            TrackSeries(
                (str(index),),
                (1, "lower", 0, 11.2e9),
                ids,
                ids,
                times,
                values,
                np.ones(len(times)),
                227272.727,
            )
        )
    return groups


def test_smooth_pair_predicts_better_joined_but_step_prefers_separate():
    smooth = compare_predictive_curves(pair())
    stepped = compare_predictive_curves(pair(1500))
    assert smooth["rms_hz"]["joined"] < 25
    assert smooth["joined_gain_hz"] > 0
    assert stepped["rms_hz"]["joined"] > 100
    assert stepped["joined_gain_hz"] < -100


def test_integer_alias_and_input_order_do_not_change_predictive_errors():
    originals = pair()
    shifted = [originals[0], replace(originals[1], values_hz=originals[1].values_hz + 227272.727)]
    a = compare_predictive_curves(originals)
    b = compare_predictive_curves(shifted[::-1])
    for mode in ("joined", "separate"):
        np.testing.assert_allclose(a["repeat_rms_hz"][mode], b["repeat_rms_hz"][mode], atol=1e-7)


def test_withheld_values_do_not_change_corresponding_training_prediction_or_degree():
    originals = pair()
    config = PredictiveCurveConfiguration(repeats=1)
    before = compare_predictive_curves(originals, config)
    blocks = before["folds"][0]["test_blocks"]
    altered = []
    for item in originals:
        values = item.values_hz.copy()
        values[np.isin(np.floor(item.times_s / config.block_s).astype(int), blocks)] += 3000
        altered.append(replace(item, values_hz=values))
    after = compare_predictive_curves(altered, config)
    for mode in ("joined", "separate"):
        a, b = (r["folds"][0]["models"][mode] for r in (before, after))
        assert a["degree"] == b["degree"]
        assert a["inner_scores"] == b["inner_scores"]
        np.testing.assert_array_equal(a["predictions_hz"], b["predictions_hz"])


def test_whole_blocks_are_withheld_and_results_repeat_exactly():
    a = compare_predictive_curves(pair())
    assert a == compare_predictive_curves(pair())
    block_ids = np.array(a["block_ids"])
    for fold in a["folds"]:
        rows = fold["models"]["joined"]["test_rows"]
        assert set(rows) == set(np.flatnonzero(np.isin(block_ids, fold["test_blocks"])))


def test_invalid_lane_and_configuration_fail_explicitly():
    with pytest.raises(ValueError):
        PredictiveCurveConfiguration(block_s=0)
    left, right = pair()
    with pytest.raises(ValueError, match="one receiver/RF lane"):
        compare_predictive_curves([left, replace(right, lane_key=(2, "lower", 0, 11.2e9))])
