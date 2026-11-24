from collections import Counter

import numpy as np
import pytest

from reports.ALGO08.v3.zero_centre_reuse import StateStamp, ZeroCentre, zero_centre_reuse


def test_state_stamp_checks_mutation_stride_and_signed_zero():
    def stamp(value):
        state = StateStamp()
        state.add(value)
        return state.digest.digest()

    source = np.zeros((2, 2))
    assert stamp(source) == stamp(source.copy())
    assert stamp(source) != stamp(source.T)
    previous = stamp(source)
    source[1, 0] = -0.
    assert previous != stamp(source)
    with pytest.raises(ValueError, match="Unsupported"):
        stamp(np.array([object()], dtype=object))


def test_only_a_paid_identical_zero_can_be_consumed_once():
    ctx = object()
    memo = ZeroCentre(ctx, Counter())
    identifiers = object(), object(), object()
    key = (b"before", *identifiers)
    node = {"seed": {"rows": [1]}, "fit": np.zeros(8)}
    assert memo.lookup(key) is None
    memo.save(key, node, 0)
    assert memo.lookup(key) is None
    memo.scouting = True
    memo.save(key, node, 0)
    node["seed"]["rows"][0] = 2
    assert memo.lookup(key) is None
    memo.scouting = False
    assert memo.lookup((b"mutated", *identifiers)) is None
    assert memo.lookup((b"before", object(), *identifiers[1:])) is None
    found = memo.lookup(key)
    assert found["seed"]["rows"] == [1]
    found["fit"][0] = 10
    assert node["fit"][0] == 0
    assert memo.lookup(key) is None
    assert memo.audit["reused"] == 1


def test_unrelated_rank_takes_original_path(monkeypatch):
    import combined_successor as combined

    expected = object()

    class Ordinary:
        scan, scout = object(), {}

        def rank(self, scan):
            return expected

    monkeypatch.setattr(combined, "SuccessorHandoff", Ordinary)
    with zero_centre_reuse():
        assert combined.SuccessorHandoff().rank(object()) is expected
    assert combined.SuccessorHandoff is Ordinary
