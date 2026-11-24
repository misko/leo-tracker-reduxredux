from collections import Counter
from contextlib import contextmanager

import pytest

import combined_successor as combined
import single_rank_refusal as refusal
import two_centre_seeds as seeds


@pytest.mark.parametrize("picked", [None, [0, 1]])
def test_only_the_true_ordinary_producer_owns_a_refused_rank(monkeypatch, picked):
    state = object.__new__(refusal.SingleRankHandoff)
    state.scan, state.scout, state.counts = object(), {}, Counter()
    state.nodes = state.checkpoint = None
    state.speculative = False
    calls, active = [], []
    nodes = [{"seed": {"rows": [{"component": "track", "candidate_index": i,
                                 "candidate_norad": i + 10}]}, "aliases": [0]} for i in range(3)]

    @contextmanager
    def trial(audit):
        active.append(audit)
        try:
            yield
        finally:
            active.pop()

    def scout(*args):
        calls.append("scout")
        return picked

    def rank(_):
        if active:
            proposals = seeds.scout(None, None, None, None, None, None, active[0])
            active[0]["paid_centres"] = len(proposals) if proposals is not None else 4
            calls.append("trial rank")
        else:
            calls.append("ordinary rank")
        return nodes

    state.exact_rank = rank
    monkeypatch.setattr(seeds, "scout", scout)
    monkeypatch.setattr(combined, "two_seeds", trial)
    with refusal.single_rank_refusal():
        assert combined.SuccessorHandoff is refusal.SingleRankHandoff
        assert state.rank(state.scan) == nodes
    assert seeds.scout is scout and not active
    if picked is None:
        assert calls == ["scout", "ordinary rank"]
        assert state.nodes == nodes and state.nodes is not nodes
        assert state.scout["paid_centres"] == 0 and not state.speculative
    else:
        assert calls == ["scout", "trial rank"]
        assert state.speculative and state.nodes is state.checkpoint is None
