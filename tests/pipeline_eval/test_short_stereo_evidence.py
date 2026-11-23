from pathlib import Path
import sys

import pytest


RESEARCH = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(RESEARCH))
try:
    from short_stereo_evidence import HORIZON, RATE, select, timing_delta, witness_offset
finally:
    sys.path.remove(str(RESEARCH))


def factor(cfo, sample, fraction=0.):
    return dict(fractional_tracking_cfo_hz=cfo, integer_epoch_sample=sample,
                fractional_epoch_offset_samples=fraction, passed_fractional_margin_gate=True)


def visit(index, first, second, *, channel=1, swap_order=False, ticks=0):
    now = (1 << 55) + index * RATE // 10
    rows = [dict(visit_index=index, receiver_id=rx, valid_start_counter=now + rx*ticks,
                 channel=channel, actual_rf_hz=11_000_000_000, edge="lower",
                 candidates=[f] if f is not None else []) for rx, f in enumerate((first, second))]
    return rows[::-1] if swap_order else rows


class History:
    def __init__(self, continued=()):
        self.continued = set(continued)
        self.seen = []

    def select(self, row):
        self.seen.append(row)
        keep = (row["visit_index"], row["receiver_id"]) in self.continued
        return None, 0 if keep else None, [3 if keep else 0]


def test_direct_signed_evidence_wraps_epoch_and_preserves_both_native_rows():
    a, b = factor(90_000, 13_332, .5), factor(90_013, 0, .125)
    rows = visit(0, a, b, swap_order=True, ticks=-1)
    assert abs(timing_delta(rows[1], rows[0], a, b)) < .3
    observed, audit = select(rows, History())
    assert observed == rows
    assert audit[0]["stereo_mode"] == "direct"
    assert all(w["rescued"] for w in audit[0]["lanes"])


def test_offset_is_causal_stream_specific_and_only_confirms_same_time():
    a, b = factor(-300_000, 10), factor(350_000, 10, .42)
    rows = [r for index in range(4) for r in visit(index, a, b, swap_order=bool(index % 2))]
    rows += visit(4, a, b, channel=2) + visit(5, a, dict(b, integer_epoch_sample=15))
    original = History()
    retained, audit = select(rows, original)
    assert original.seen == rows
    assert [w["stereo_mode"] for w in audit] == [None, None, None, "prior_offset", None, None]
    assert sum(bool(row["candidates"]) for row in retained) == 2
    assert audit[3]["prior_offset_hz"] == 650_000
    assert audit[5]["timing_match"] is False


def test_negative_control_does_not_match_unsigned_carriers_or_copy_mate():
    a, b = factor(-50_000, 0), factor(50_000, 0)
    rows = visit(0, a, b) + visit(1, None, b)
    retained, audit = select(rows, History(continued={(0, 0)}))
    assert audit[0]["timing_match"] and audit[0]["stereo_mode"] is None
    assert [row["candidates"] for row in retained] == [[a], [], [], []]


def test_empty_opportunities_and_timeout_expire_the_witnesses():
    offset = [(1, 620_000.), (2, 620_004.), (3, 620_003.)]
    assert witness_offset(offset, HORIZON + 1) == 620_003.
    assert witness_offset(offset, HORIZON + 2) is None
    assert witness_offset([(1, 100.), (2, 101.), (3, 2_000.)], 4) is None
    a, b = factor(-300_000, 10), factor(350_000, 10, .42)
    rows = sum((visit(i, a, b) for i in range(3)), [])
    rows += sum((visit(i, None, None) for i in range(3, 15)), []) + visit(15, a, b)
    _, audit = select(rows, History())
    assert audit[-1]["prior_offset_hz"] is None


def test_mate_must_share_the_original_stream():
    rows = visit(0, None, None)
    rows[1]["edge"] = "upper"
    with pytest.raises(ValueError, match="same RF"):
        select(rows, History())
