import pytest

from tools.pipeline_eval.qualification import accelerated_command_parity as original
from tools.pipeline_eval.qualification import portable_field_parity as parity


def peak(rank, epoch, cfo, gate):
    return dict(
        candidate_rank=rank,
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0.125,
        fractional_tracking_cfo_hz=cfo,
        passed_fractional_margin_gate=gate,
    )


def probe(peaks):
    return dict(visit_index=0, receiver_id=0, probe_index=0, probe_start_ms=0, candidates=peaks)


def native(probes, clock):
    return dict(
        schema_version=2,
        clock_anchor={"sample_counter": 100},
        delivery_clocks=[clock],
        last_sample_counter=200,
        source=dict(probes=probes, analysis_manifest_sha256="digest"),
        provenance=dict(excluded_windows=[]),
    )


def test_complete_parity_distinguishes_gate_change_and_ambiguous_alias():
    clock = dict(monotonic_ns=100, realtime_ns=500)
    old = [probe([peak(0, 5_272_995_756_195, 42, True), peak(1, 5_272_995_756_195, 42, False)])]
    live = [
        probe(
            [
                peak(0, 5_272_995_756_195, 42 + original.ALIAS, False),
                peak(1, 5_272_995_756_195, 42 + original.ALIAS, False),
            ]
        )
    ]
    fresh, stock = native(live, clock), native(old, clock)
    visits = [
        dict(
            visit=0,
            status="processed",
            probes=live,
            delivery_clock=clock,
            clock_anchor=fresh["clock_anchor"],
            sample_end=200,
        )
    ]
    proof, changes, ambiguity = parity.compare(fresh, visits, stock)
    assert proof["coverage"] == "complete_native"
    assert proof["gate_counts"]["matched_gate_changed"] == 1
    assert proof["rank_counts"]["unmatched_archived"] == 0
    assert proof["physical_neighbourhood"]["ambiguous_changed_probes"] == 1
    assert proof["physical_neighbourhood"]["matched_absolute_error"]["circular_cfo_hz"][
        "max"
    ] == pytest.approx(0.0, abs=1e-8)
    assert set(ambiguity[0]["equivalent_indices"]) == {(0, 0), (1, 0), (0, 1), (1, 1)}
    assert (
        "passed_fractional_margin_gate"
        in changes[0]["matched_peak_axes"][0]["exact_fields_changed"]
    )
    visits[0]["sample_end"] = 201
    with pytest.raises(ValueError, match="handoff"):
        parity.compare(fresh, visits, stock)


def test_missing_chunk_does_not_report_full_native_coverage():
    clock = dict(monotonic_ns=100, realtime_ns=500)
    report, _, _ = parity.compare(None, [], native([], clock))
    assert report["coverage"] == "closed_chunks_only"
    assert report["archived_total_visits"] == 1
    assert report["compared_visits"] == 0
    assert report["first_clock_anchor_matches"] is None
