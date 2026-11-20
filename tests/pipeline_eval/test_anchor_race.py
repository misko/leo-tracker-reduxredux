import numpy as np

from tools.pipeline_eval.variants import anchor_race


def test_minimum_consensus_and_unilateral_bright_hypotheses_have_separate_slots(monkeypatch):
    monkeypatch.setattr(anchor_race, "CAP", 3)
    monkeypatch.setattr(anchor_race, "CONSENSUS", 1)
    a, b = np.zeros((1, 43)), np.zeros((1, 43))
    a[0, [3, 9, 28, 32]] = [0.9, 0.5, 0.18, 0.12]
    b[0, [3, 9, 28, 32]] = [0.02, 0.6, 0.87, 0.15]
    votes, persistent, _ = anchor_race.nominate(a, b, (0,), 1, 80_000, "race", None)
    assert [v[1] for v in votes] == [9, 3, 28]
    assert persistent == 1


def test_sham_rotates_identical_budget_without_changing_proposal_weights(monkeypatch):
    monkeypatch.setattr(anchor_race, "CAP", 3)
    monkeypatch.setattr(anchor_race, "CONSENSUS", 1)
    a, b = np.zeros((1, 73)), np.zeros((1, 73))
    a[0, [0, 36, 59]] = [2, 3, 5]
    b[0, [0, 36, 59]] = [1, 4, 3]
    args = (a, b, (0,), 1, 80_000)
    captured, support, _ = anchor_race.nominate(*args, "race", "same-visit")
    sham, new_support, shift = anchor_race.nominate(*args, "sham", "same-visit")
    assert support == new_support == 1
    assert 0 < shift < 73
    assert sham == [(s, (e + shift) % 73, f) for s, e, f in captured]
    assert sum(b - a for a, b in anchor_race.intervals(73, captured)) == sum(
        b - a for a, b in anchor_race.intervals(73, sham)
    )


def test_suppression_uses_circular_epoch_and_stable_frequency_order():
    scores = np.zeros((3, 40))
    scores[0, [2, 23]] = [1, 1]
    scores[1, 38] = 1
    scores[2, 23] = 1
    retained = anchor_race.top(scores, (-80_000, 0, 80_000), 8, 5, 80_000)
    assert retained == [(1.0, 38, 0.0), (1.0, 23, -80_000.0), (1.0, 23, 80_000.0)]
