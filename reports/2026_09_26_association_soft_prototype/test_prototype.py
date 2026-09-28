from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

SPEC = importlib.util.spec_from_file_location("prototype", Path(__file__).with_name("run_prototype.py"))
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _track(rms, *, weight=2):
    return {
        "track_id": "t",
        "weight_s": weight,
        "candidates": [
            {"candidate_id": str(index + 1), "heldout_rms_hz": value}
            for index, value in enumerate(rms)
        ],
    }


def test_rejection_is_conservative_for_zero_or_one_candidate():
    for rms in ([], [10.0]):
        scores = MODULE._scores([_track(rms)])
        assert scores["reject_m5"] == MODULE.CAP_HZ


def test_exact_margin_boundary_is_accepted_and_fixed_denominator_is_preserved():
    scores = MODULE._scores([_track([10.0, 15.0], weight=1), _track([], weight=3)])
    expected = np.sqrt((10.0**2 + 3 * MODULE.CAP_HZ**2) / 4)
    assert np.isclose(scores["reject_m5"], expected)
    assert scores["reject_m10"] == MODULE.CAP_HZ


def test_soft_small_temperature_converges_to_hard_and_permutation_is_invariant():
    original = (_track([10.0, 200.0]), _track([20.0, 300.0], weight=4))
    left = MODULE._scores(list(original))
    right = MODULE._scores(list(reversed(original)))
    assert left == right
    hard = np.sqrt((2 * 10.0**2 + 4 * 20.0**2) / 6)
    assert np.isclose(left["hard"], hard)
    assert abs(left["soft_T5"] - hard) < 1e-10


def test_candidate_rows_merge_distinct_identity_globally_across_blocks():
    class Block:
        track_id = "t"
        observation_ids = tuple(str(i) for i in range(6))
        times_s = np.arange(6.0)
        measured_hz = np.zeros(6)
        training_mask = np.asarray([True, True, True, False, False, False])
        taus_s = np.asarray([0.0])

        def __init__(self, candidate_ids, values):
            self.candidate_ids = np.asarray(candidate_ids)
            self.predictions_hz = np.asarray(values, dtype=float)[:, None, :]
            self.visible = np.ones(len(candidate_ids), dtype=bool)

    # ID 2 appears in both blocks; its lower held-out RMS must survive once.
    first = Block([1, 2], [[0, 0, 0, 1, 1, 1], [0, 0, 0, 4, 4, 4]])
    second = Block([2, 3], [[0, 0, 0, 2, 2, 2], [0, 0, 0, 3, 3, 3]])
    rows = MODULE._candidate_rows((first, second))
    assert set(rows) == {"1", "2", "3"}
    assert rows["2"]["heldout_rms_hz"] == 2.0


def test_all_invisible_candidates_produce_empty_inventory_without_nan():
    class Block:
        track_id = "t"
        observation_ids = tuple(str(i) for i in range(6))
        times_s = np.arange(6.0)
        measured_hz = np.zeros(6)
        training_mask = np.asarray([True, True, True, False, False, False])
        taus_s = np.asarray([0.0])
        candidate_ids = np.asarray([1])
        predictions_hz = np.zeros((1, 1, 6))
        visible = np.asarray([False])

    assert MODULE._candidate_rows((Block(),)) == {}
