"""Check signed parity after either EOF route on a fixed lane sequence."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from continued_cfo_live_trial import compare, staged_seal_after_decision
from held_cycle_refined import CFO


@pytest.mark.parametrize("route", ["history", "unfiltered"])
def test_same_causal_prefix_pays_only_supported_rows_and_preserves_the_selected_payload(route):
    original = [dict(visit_index=i, receiver_id=0, channel=1, actual_rf_hz=10_000_000.,
                     valid_start_counter=i*10_000_000,
                     candidates=[{CFO: 1000.+100*i, "fractional_margin": .3, "candidate_rank": 0}])
                for i in range(4)]
    all_paid = [dict(p, candidates=[dict(p["candidates"][0], **{CFO: p["candidates"][0][CFO]+1})]) for p in original]
    selective = original[:3] + all_paid[3:]
    choice = dict(route=route, log_score_gain_by_radio={"0": 1., "1": 1.})
    shared = dict(iq=[1, 2], vectors=[dict(visit=i,lane=0,mode="short_primary") for i in range(4)],
                  prefix_inventory="manifest", original_probes=original, held_cycle_decision={"choice":choice})

    def scope(acquired, count):
        return dict(shared, acquired_probes=acquired, policy_clocks=dict(probes=4, paid=count),
                    receiver_audit=dict(native=dict(cfo_refinement=dict(lanes=[
                        dict(counts=dict(attempted=count, changed=count))]))))

    def packet(probes, pin):
        return dict(clock_anchor="capture", delivery_clocks="signed", provenance=dict(detector_sha256=pin),
                    source=dict(probes=probes, raw_recording_authority_digest="recording"))

    a, c = scope(all_paid, 4), scope(selective, 1)
    if route == "history":
        selected = [dict(p, candidates=[]) for p in original[:3]] + all_paid[3:]
        old, new = packet(selected, "all"), packet(selected, "gated")
    else:
        old, new = packet(all_paid, "all"), packet(selective, "gated")
    result = compare(a, c, old, new)
    assert result["counts"]["all_paid_attempts"] == 4
    assert result["counts"]["selective_attempts"] == 1
    assert result["counts"]["skipped_edits"] == 3
    assert result["selected_payload_equal"] == (route == "history")
    wrong = dict(c, policy_clocks=dict(c["policy_clocks"], probes=3))
    with pytest.raises(ValueError, match="advance on every"):
        compare(a, wrong, old, new)


def test_source_binding_rejects_unreviewed_worker_shape():
    with pytest.raises(ValueError, match="source-pinned staged seal"):
        staged_seal_after_decision("def another_worker(): pass")
