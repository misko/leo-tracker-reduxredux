import pytest

from tools.pipeline_eval.qualification import prefix_evidence_trial as trial
from tools.pipeline_eval.variants import prefix_evidence as prefix

RATE = 10_000_000
ANCHOR = 23_998_797_995_731
DWELL = RATE // 50
CUTOFF = ANCHOR + prefix.SECONDS * RATE


def probe(i, start, channel=1, retune=0, candidate=True, rx=0):
    peak = dict(
        integer_epoch_sample=509,
        fractional_epoch_offset_samples=0.17,
        fractional_tracking_cfo_hz=1500 - retune,
        passed_fractional_margin_gate=True,
    )
    return dict(
        visit_index=i,
        valid_start_counter=start,
        probe_start_ms=0,
        channel=channel,
        receiver_id=rx,
        edge="lower",
        actual_rf_hz=10_700_000_000 + retune,
        candidates=[peak] if candidate else [],
    )


def test_retune_corrected_frequency_on_real_sized_clock_retains_recurrence():
    rows = [probe(i, ANCHOR + i * 4_000_000, retune=7000 * i) for i in range(3)]
    ends, _ = prefix.support(rows, RATE, DWELL, ANCHOR, CUTOFF)
    assert ends == {(2, 0): 0}
    rows[-1]["candidates"][0]["fractional_tracking_cfo_hz"] += 7000
    assert not prefix.support(rows, RATE, DWELL, ANCHOR, CUTOFF)[0]


def test_choose_fifth_only_when_both_halves_and_multiple_lanes_agree():
    rows = []
    for half in (0, 1):
        for i in range(5):
            for lane in (0, 1):
                rows.append(probe(len(rows), ANCHOR + half * 12 * RATE + i * 4_000_000, rx=lane))
    blank = [dict(p, candidates=[]) for p in rows]
    choice = prefix.decide(blank, rows, RATE, DWELL, ANCHOR, CUTOFF)
    assert choice["chosen"] == "fifth"
    assert choice["net_by_half"] == [6, 6]
    assert prefix.decide(rows, rows, RATE, DWELL, ANCHOR, CUTOFF)["chosen"] == "stock"
    assert prefix.decide(blank, rows[:10], RATE, DWELL, ANCHOR, CUTOFF)["chosen"] == "stock"


def test_straddling_visit_is_stock_and_never_used_to_decide():
    before = probe(0, CUTOFF - DWELL // 2)
    after = probe(1, CUTOFF)
    stock = dict(
        schema_version=2,
        clock_anchor={"sample_counter": ANCHOR},
        delivery_clocks=[],
        last_sample_counter=CUTOFF + DWELL,
        source=dict(sample_rate_hz=RATE, probe_ms=20, probes=[before, after]),
        provenance={"detector_sha256": "stock"},
    )
    fifth = dict(
        stock,
        source=dict(
            stock["source"],
            probes=[
                dict(before, candidates=[]),
                dict(after, candidates=[]),
            ],
        ),
        provenance={"detector_sha256": "fifth"},
    )
    assert not trial.available(stock, RATE, DWELL, CUTOFF)
    mixed, counts = trial.materialize(
        stock,
        fifth,
        dict(chosen="fifth", anchor=ANCHOR, cutoff=CUTOFF),
        dict(stock={"sha256": "s"}, fifth={"sha256": "f"}),
    )
    assert mixed["source"]["probes"] == [before, fifth["source"]["probes"][1]]
    assert counts["fifth_probes"] == 1
    changed = dict(
        fifth,
        source=dict(
            fifth["source"],
            probes=[
                dict(before, edge="upper"),
                after,
            ],
        ),
    )
    with pytest.raises(ValueError, match="Physical probe coordinates"):
        trial.paired_support(stock, changed)
