import pytest

from tools.pipeline_eval.qualification.coherent_peak_scores import losses
from tools.pipeline_eval.qualification.coherent_peak_trial import MATCHED, roster
from tools.pipeline_eval.variants.coherent_peak_filter import FOLD_HZ, filter_document

FS = 10_000_000
RF = 11_440_312_500
PERIOD = FS / 750
ORIGIN = 9_542_673_000_000


def fold(value):
    return value - FOLD_HZ * round(value / FOLD_HZ)


def probe(visit, t, *, choices=((0, 0.80, True),), receiver=0, offset_ms=0):
    # Linear range acceleration plus independent sample-clock drift. The
    # starting CFO crosses a fold boundary and neither phase nor drift is zero.
    initial_hz, slope_hz_s = 113_000, 1700
    carrier = fold(initial_hz + slope_hz_s * t)
    absolute_epoch = 4300 + 42 * t - FS / RF * slope_hz_s * t**2 / 2
    start = ORIGIN + round(t * FS)
    local_epoch = (absolute_epoch - (start % PERIOD)) % PERIOD
    return dict(
        receiver_id=receiver,
        channel=3,
        actual_rf_hz=RF,
        visit_index=visit,
        valid_start_counter=start - round(offset_ms / 1000 * FS),
        probe_start_ms=offset_ms,
        candidates=[
            dict(
                integer_epoch_sample=round(local_epoch + delay),
                fractional_epoch_offset_samples=local_epoch + delay - round(local_epoch + delay),
                fractional_tracking_cfo_hz=carrier,
                fractional_margin=margin,
                candidate_rank=rank,
                passed_fractional_margin_gate=gate,
            )
            for rank, (delay, margin, gate) in enumerate(choices)
        ],
    )


def document(*probes):
    return dict(source=dict(sample_rate_hz=FS, probe_ms=20, probes=list(probes)), schema_version=2)


def test_unique_folded_continuation_preserves_mark_and_original_support():
    original = document(
        probe(1, 0),
        probe(2, 0.8, offset_ms=20),
        probe(3, 1.75, choices=((21, 0.9, True), (0, 0.4, True), (25, 0.02, False))),
    )
    result, counts = filter_document(original)
    before, after = original["source"]["probes"], result["source"]["probes"]
    assert after[:2] == before[:2]
    assert after[2] | {"candidates": before[2]["candidates"]} == before[2]
    assert after[2]["candidates"] == before[2]["candidates"][1:]
    assert len(before[2]["candidates"]) == 3
    assert counts["passing_before"] == 4
    assert counts["passing_after"] == 3
    assert counts["changed_winners"] == 1
    assert counts["positive_probes"] == 3


def test_causal_ambiguous_missing_other_lane_and_same_visit_are_unchanged():
    rows = (
        probe(1, 0),
        probe(2, 0.8),
        probe(3, 1.75, choices=((0, 0.9, True), (1, 0.4, True))),
        probe(3, 1.77, choices=((20, 0.9, True), (0, 0.4, True))),
        probe(3, 1.77, receiver=1, choices=((20, 0.9, True), (0, 0.4, True))),
        probe(4, 6, choices=((20, 0.9, True), (0, 0.4, True))),
    )
    streaming, counts = filter_document(document(*rows))
    assert streaming == document(*rows)
    assert counts["reduced_probes"] == 0
    for length in range(len(rows)):
        prefix, _ = filter_document(document(*rows[:length]))
        assert streaming["source"]["probes"][:length] == prefix["source"]["probes"]
    with pytest.raises(ValueError, match="increase"):
        filter_document(document(rows[1], rows[0]))


def test_changed_winner_cannot_seed_its_own_confirmation():
    rows = (
        probe(1, 0),
        probe(2, 0.8),
        probe(3, 1.75, choices=((100, 0.9, True), (0, 0.4, True))),
        probe(4, 2.5, choices=((20, 0.9, True), (0, 0.4, True))),
    )
    result, counts = filter_document(document(*rows))
    assert result["source"]["probes"][-1] == rows[-1]
    assert counts["changed_winners"] == 1


def test_heldout_roster_ranks_eligible_ordinary_receipts_by_family():
    available = list(MATCHED) + ["DS26-0122", "DS29-0247", "DS27-9999"]
    assert roster(dict.fromkeys(available)) == sorted(available[:-1])


def test_scoring_distinguishes_withhold_from_execution_failure():
    strict = [dict(id=ident, status="ok", publication=True) for ident in ("a", "b", "c")]
    filtered = [
        dict(id="a", status="withheld", publication=False),
        dict(id="b", status="timed_out", publication=False),
        dict(id="c", status="ok", publication=True),
    ]
    summary = losses(filtered, strict)
    assert summary["strict_fix_lost_to_withhold"] == ["a"]
    assert summary["strict_fix_lost_to_deadline"] == ["b"]
