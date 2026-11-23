import pytest

from reports.ALGO08.v3.full_short_cfo_only import CFO, substitute_cfo


def test_only_close_nonanchor_cfo_changes_and_original_packets_survive():
    template = dict(candidate_rank=0, integer_epoch_sample=12, fractional_epoch_offset_samples=-.12,
                    fractional_exact_score=.19, fractional_control_score=.04, fractional_margin=.15,
                    passed_fractional_margin_gate=True)
    short = dict(template, **{CFO: 83_600.})
    stock = dict(template, candidate_rank=1, fractional_epoch_offset_samples=.25, fractional_margin=.12,
                 **{CFO: 83_720.})
    probes = [dict(visit_index=i // 2, channel=1, receiver_id=i % 2) for i in range(6)]
    descriptions = [(stock, short, "matched", False), (stock, short, "matched", True),
                    (stock, short, "changed_identity", False), (None, short, "mixed_only", False),
                    (stock, None, "stock_only", False), (None, None, "empty", False)]
    rows = [(lane, *description) for lane, description in zip(probes, descriptions, strict=True)]
    output, changed = substitute_cfo(rows)

    assert output == [dict(lane, candidates=factors) for lane, factors in zip(probes,
        [[dict(short, **{CFO: 83_720.})], [short], [short], [short], [], []], strict=True)]
    assert changed == [dict(visit=0, radio=0, channel=1, original_hz=83_720., mixed_hz=83_600.)]
    assert short[CFO] == 83_600. and stock["candidate_rank"] == 1


def test_invalid_replacement_cfo_fails_closed():
    with pytest.raises(ValueError, match="must be finite"):
        substitute_cfo([(dict(), {CFO: float("nan")}, {CFO: -1.0}, "matched", False)])
