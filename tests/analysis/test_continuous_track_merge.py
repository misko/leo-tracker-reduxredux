from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.continuous_track_merge import (
    ContinuousMergeConfiguration,
    TrackSeries,
    evaluate_join,
    merge_tracks,
)


def pair(step=0, slope=0, gap=1.4):
    a = np.arange(0, 24, 0.5)
    b = np.arange(a[-1] + gap, 46, 0.5)
    noise = np.random.default_rng(8).normal(0, 15, len(a) + len(b))
    tracks = []
    for index, times in enumerate((a, b)):
        start = 0 if index == 0 else len(a)
        y = 100000 - 2000 * times + 15 * times**2 + 0.03 * times**3
        y += noise[start : start + len(times)]
        if index:
            y += 227272.727 + step + slope * (times - (a[-1] + b[0]) / 2)
        ids = tuple(f"{index}:{i}" for i in range(len(times)))
        tracks.append(
            TrackSeries(
                (str(index),),
                (1, "lower", 0, 11.2e9),
                ids,
                ids,
                times,
                y,
                np.ones(len(times)),
                227272.727,
            )
        )
    return tracks


def test_continuous_alias_shifted_pair_is_joined_without_free_offset():
    merged, receipt = evaluate_join(*pair())
    assert receipt["accepted"] and receipt["alias_shift"] == -1
    assert merged is not None and len(merged.source_ids) == sum(len(t.source_ids) for t in pair())
    assert receipt["held_rms_hz"] < 30


@pytest.mark.parametrize("step,slope", [(2000, 0), (0, 100)])
def test_discontinuity_guard_rejects_false_join(step, slope):
    merged, receipt = evaluate_join(*pair(step, slope))
    assert merged is None
    assert receipt["reason"] in ("boundary-discontinuity", "endpoint-frequency")


def test_gap_and_lane_rules_are_enforced():
    left, right = pair(gap=8.1)
    assert evaluate_join(left, right)[1]["reason"] == "gap-or-overlap"
    assert (
        evaluate_join(left, replace(right, lane_key=(2, "lower", 0, 11.2e9)))[1]["reason"]
        == "different-lane"
    )


def test_input_order_does_not_change_greedy_result():
    forward, _ = merge_tracks(pair())
    reverse, _ = merge_tracks(tuple(reversed(pair())))
    assert [t.member_ids for t in forward] == [t.member_ids for t in reverse]


def test_configuration_and_duplicate_observations_are_validated():
    with pytest.raises(ValueError):
        ContinuousMergeConfiguration(maximum_gap_s=-1)
    left, _ = pair()
    with pytest.raises(ValueError, match="reuses"):
        replace(left, source_ids=(left.source_ids[0],) * len(left.source_ids))
