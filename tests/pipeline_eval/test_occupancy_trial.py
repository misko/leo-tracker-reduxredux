import math

import numpy as np
import pytest

from reports.ALGO08.v3.occupancy_trial import FEATURES, TILE_INDEX, assignments, calibration, cutoff, evaluate, scores


def test_blind_features_are_scale_normalized_and_repetition_ignores_frame_phase():
    rng = np.random.default_rng(913)
    iq = rng.integers(-500, 500, (200000, 2, 2), dtype=np.int16)
    old = scores(iq, 0)
    assert scores(iq*3, 0) == pytest.approx(old)
    repeated = rng.integers(-300, 300, (8, 96, 2), dtype=np.int16)
    for frame, indices in enumerate(TILE_INDEX):
        iq[indices, 0] = repeated if frame % 2 == 0 else np.stack((-repeated[..., 1], repeated[..., 0]), axis=2)
    measured = scores(iq, 0)
    assert measured["frame_repetition"] == pytest.approx(1.)
    assert measured["frame_repetition"] > old["frame_repetition"]
    assert scores(np.zeros_like(iq), 0) == dict.fromkeys(FEATURES, 0.)


def test_threshold_keeps_ties_and_oracle_cost_excludes_unselected_donors():
    def row(score, factors, selected=None):
        return dict(scores={k: score for k in FEATURES}, factors=factors, selected=selected,
                    native_cpu_ns=100, screen_cpu_ns=10)

    rows = [row(2., [1]), row(3., [1], 1), row(2., []), row(1., [])]
    assert cutoff(rows, FEATURES[0], 1.) == 2.
    assert cutoff(rows, FEATURES[0], .5) == 3.
    feature, threshold, evidence = calibration(rows)
    assert feature == FEATURES[0] and threshold == 2.
    assert evidence[feature]["perfect_empty_cpu_saved_ns"] == 200
    assert evidence[feature]["net_cpu_saved_ns"] == 60
    result = evaluate(rows, [False, True, False, False])
    assert result["counts"]["donor_skipped"] == 1
    assert result["counts"]["missed_lanes"] == 1
    assert math.isinf(cutoff(rows[2:], FEATURES[0], 1.))


def test_seed_picks_whole_distinct_members():
    picked = assignments()
    assert {picked["dense_development"], picked["dense_held"]} == {0, 64}
    assert picked["dense_later"] in (512, 640, 768, 896)
