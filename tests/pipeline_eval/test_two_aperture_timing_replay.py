import json

import pytest

from reports.ALGO08.v3 import two_aperture_timing_replay as replay


def factor(epoch, cfo):
    return [{"integer_epoch_sample": epoch, "fractional_epoch_offset_samples": 0,
             "fractional_tracking_cfo_hz": cfo}]


def test_matching_wraps_fractional_epoch_and_never_folds_signed_frequency():
    assert replay.same_measurement((13_332.75, -9500), (0.25, -9250))
    assert not replay.same_measurement((13_332.75, -9500), (0.25, 9500))
    assert not replay.same_measurement((13_332.75, -9500), (2.25, -9500))
    assert not replay.same_measurement(None, (0.25, -9500))


def test_pricing_keeps_shared_anchors_and_counts_displaced_positives():
    clocks = {"8-primary": [2, 3], "20-primary": [5, 6], "20-two": [9, 11]}
    first = factor(100, -9000)
    displaced = factor(100, 9000)
    rows = [
        dict(anchor=anchor, clocks=clocks, alternatives={"8-primary": s, "20-primary": l})
        for anchor, s, l in [(True, [], first), (False, [], first), (False, [], []),
                              (False, displaced, first), (False, first, first)]
    ]
    result = replay.main_prices(rows)
    assert result["original_native_cpu_wall_ns"] == {
        "8-primary": [17, 23], "20-primary": [29, 35], "20-two": [45, 55],
    }
    assert result["added_retries_cpu_wall_ns"] == {
        "all_short_empty": [10, 12], "oracle_all_missed_primary": [10, 12],
        "oracle_recovered_empties": [5, 6],
    }
    assert result["lanes"]["short_matches_full_primary"] == 1
    assert result["all_lane_rescue_budget_cpu_ns"] == 3


def test_replay_requires_exact_original_lane_metadata():
    key = "DS30-0008:0"
    short = {(key, 0): ("iq", "low", 100, 10, None)}
    full = [dict(kind="full", key=key, scheduled="short", antenna=0, iq="iq",
                 edge="low", sample=101, rf=10, factors=[])]
    folded = dict(inputs=[(key, "iq")], misses=[])
    with pytest.raises(ValueError, match="identical source samples"):
        replay.proposal_coverage(short, full, folded, "dense")


def test_sealed_replay_is_exact_and_marks_generous_incomplete_support():
    result = replay.audit()
    saved = json.loads((replay.MEASUREMENTS / "two-aperture-timing-replay.json").read_text())
    assert json.loads(json.dumps(result)) == saved
    assert result["waveform_bytes"] == result["new_native_runs"] == 0
    for cohort, misses, differential in (("dense", 9, 6), ("weak", 8, 6)):
        counts = result["independent_timing"][cohort]["counts"]
        assert counts["short_unmatched/factors"] == misses
        assert counts["short_unmatched/short_or_full_top4_phase"] == misses
        assert counts["short_unmatched/short_or_differential_phase"] == differential
