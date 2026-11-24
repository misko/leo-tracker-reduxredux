"""The selective full recheck depends only on established past continuation."""

from pathlib import Path
import json
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from selective_full_recheck import replace, shortlist
from selective_full_recheck_score import stats


def row(visit, counter, values, radio=0):
    return dict(visit_index=visit, receiver_id=radio, channel=4, edge="lower", actual_rf_hz=10e9,
                valid_start_counter=counter, candidates=values)


class History:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.rows = []

    def select(self, row):
        self.rows.append(row)
        return next(self.outcomes)


def test_zero_vote_gate_requires_live_past_on_exact_lane_and_advances_empties():
    rows = [row(0, 1, [1]), row(1, 2, []), row(2, 3, [2], 1), row(3, 4, [3]), row(4, 90_000_001, [4])]
    entries = [(i, 1, x["receiver_id"], None, "short", None) for i, x in enumerate(rows)]
    history = History([(0, 0, [3]), (None, None, []), (0, None, [0]), (0, None, [0]), (0, None, [0])])
    selected, evidence = shortlist(rows, entries, history)
    assert selected == {(3, 0)}
    assert history.rows == rows
    assert [record["same_lane_prior_kept"] for record in evidence] == [0, 1, 0, 1, 0]


def test_full_temporal_rule_can_keep_second_candidate_or_emit_empty():
    rows = [row(0, 11, [1]), row(1, 12, [2]), row(2, 13, []), row(3, 14, [3])]
    history = History([(0, None, [0]), (1, 1, [0, 3]), (None, None, []), (None, None, [])])
    output, _ = replace(rows, {(1, 0): [10, 11], (3, 0): []}, history)
    assert [probe["candidates"] for probe in output] == [[1], [11], [], []]
    assert [probe["candidates"] for probe in history.rows] == [[1], [10, 11], [], []]


def test_named_lane_agreement_and_exact_measurement_agreement_are_distinct():
    named = {(0, 0): [{"cfo": -0.0}], (1, 0): []}
    candidate = {(0, 0): [{"cfo": 0.0}], (1, 0): [{"cfo": 3.0}]}
    result = stats(named, candidate, json.dumps)
    assert result["lane"]["recall"] == 1.0 and result["lane"]["precision"] == .5
    assert result["factor"]["recall"] == 0 and result["factor"]["shared"] == 0
