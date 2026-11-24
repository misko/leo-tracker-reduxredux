"""Check the complete original chronology and the paid correction witness."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from continued_cfo import ContinuedChanges, lane_key
from held_cycle_refined import CFO, FACTOR_FIELDS


def probe(i, radio=0, frequency=None):
    candidates = []
    if frequency is not None:
        candidates = [dict(zip(FACTOR_FIELDS, (0, 100, .25, frequency, .4, .1), strict=True),
                           fractional_margin=.3, passed_fractional_margin_gate=True)]
    return dict(visit_index=i, receiver_id=radio, valid_start_counter=i*10_000_000,
                channel=1, actual_rf_hz=10_000_000, edge="lower", candidates=candidates)


def test_rejected_original_positives_and_an_unpaid_anchor_advance_physical_history():
    select = ContinuedChanges()
    rows = [probe(i, frequency=1000.+100*i) for i in range(4)]
    assert [select.consider(row, short=(i>0)) for i,row in enumerate(rows)] == [False, False, False, True]
    assert select.paid == [lane_key(rows[3])]
    assert [bool(row["candidates"]) for row in select.projected_history(rows)] == [False, False, False, True]
    for i in range(4, 16):
        assert not select.consider(probe(i), short=True)
    assert not select.consider(probe(16, frequency=2600.), short=True)


def test_only_paid_corrections_restore_original_pre_cfo_history():
    select = ContinuedChanges()
    rows = [probe(i, radio=r, frequency=1000.+100*i if r == 0 else None)
            for i in range(4) for r in (0,1)]
    assert [select.consider(row, short=row["visit_index"]>0) for row in rows].count(True) == 1
    source = tuple(rows[6]["candidates"][0][k] for k in FACTOR_FIELDS)
    def amend(factors):
        (item,) = factors
        return ((item[:3]+(2400.,)+item[4:]),), "updated"

    policy = SimpleNamespace(amend=amend)
    with select.capture(policy):
        assert policy.continued_changes is select
        (revised,), _ = policy.amend((source,))
    assert not hasattr(policy, "continued_changes")
    native = [*rows]
    native[6] = dict(rows[6], candidates=[dict(rows[6]["candidates"][0], **{CFO: revised[3]})])
    packet = dict(source=dict(probes=native), provenance=dict(processed_windows=4, invalid_capture=0, window_count=4))
    select.bind_attempts(packet)
    assert select.original_rows(native) == rows
    assert select.projected_history(native)[6]["candidates"][0][CFO] == 2400.
    with pytest.raises(ValueError, match="different signed chronology"):
        select.projected_history(native[::-1])
