import pytest

from reports.ALGO08.v3.short_primary_fusion_profile import ShortTrace, STAGES, causal_overlap, projection


def test_trace_has_an_explicit_remainder_and_rejects_overlapping_clocks():
    trace = ShortTrace()
    trace.ns[0], trace.ns[7], trace.total = 2, 4, 10
    trace.gate_ns[0] = 3
    assert trace.document()["ns"]["other"] == 4
    trace.gate_ns[0] = 5
    with pytest.raises(ValueError, match="inconsistent exclusive stage totals"):
        trace.document()


def test_overlap_uses_the_actual_bank_winner_and_original_signed_frequency():
    trace = dict(verifier_epoch=2, confirmed_epoch=2, witness=0, confirmed_hz=-95.0, verifier_hz=-95.0,
                 winner_request=1, bank=[(2, -95.0), (13332, -101.0)])
    audit = causal_overlap(trace)
    assert audit["same_gate_center"] and audit["bank_center_in_full_rate_grid"]
    assert audit["bank_to_verify_delta_samples"] == 3 and audit["bank_to_verify_delta_hz"] == 6.0
    assert not audit["same_bank_frequency"]
    with pytest.raises(ValueError, match="actual confirmed scout seed"):
        causal_overlap(dict(trace, verifier_hz=95.0))


def test_projection_binds_to_actual_short_cpu_and_preserves_disjoint_boundaries():
    stages = dict.fromkeys((*STAGES, "other"), 100)
    stats = {"grouped": {
        "empty": dict(stage_ns_per_lane=stages, optimistic_early_reuse_ns_per_lane=0),
        "positive": dict(stage_ns_per_lane=dict(stages, input_mix=300), optimistic_early_reuse_ns_per_lane=50),
    }}
    observed = projection(stats, 4, 10, 2.0, 11.0, 16.0, 10.0, 15.0)
    assert sum(observed["attributed_s"].values()) == pytest.approx(2.0)
    assert observed["projections"]["entire_short_primary"]["candidate_elapsed_floor"] == 9.0
    early = observed["projections"]["same_support_early_confirmation"]["cpu_saved"]
    assert 0 < early < observed["projections"]["all_early_and_late_confirmation"]["cpu_saved"]
