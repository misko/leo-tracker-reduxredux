from tools.pipeline_eval.qualification import accelerated_command_parity as model
from tools.pipeline_eval.qualification.accelerated_command_results import partial_parity


def candidate(rank, time, freq, gate=True):
    return {
        "candidate_rank": rank,
        "integer_epoch_sample": time,
        "fractional_epoch_offset_samples": 0.0,
        "fractional_tracking_cfo_hz": freq,
        "passed_fractional_margin_gate": gate,
    }


def factors(peaks, visit=0):
    return {
        "schema_version": 2,
        "clock_anchor": 1,
        "source": {
            "probes": [
                {
                    "visit_index": visit,
                    "receiver_id": 0,
                    "probe_index": 0,
                    "probe_start_ms": 0,
                    "candidates": peaks,
                }
            ]
        },
        "provenance": {},
    }


def test_changed_peaks_keep_candidate_correspondence_and_report_reordering():
    archive = factors([candidate(0, 10, 42), candidate(1, 13, 320)])
    proof, changes = model.compare(
        factors([candidate(0, 13, 320.02), candidate(1, 10, 42.01, False)]),
        archive,
    )
    assert proof["physical_probe_metadata_changes"] == 0
    assert proof["rank_counts"]["rank_id_sequence_changed"] == 0
    assert proof["rank_counts"]["matched_rank_changed"] == 2
    assert proof["rank_counts"]["probes_with_reordered_matches"] == 1
    assert proof["gate_counts"]["matched_gate_changed"] == 1
    assert changes[0]["matched_physical_indices"] == [(0, 1), (1, 0)]


def test_alias_correspondence_and_duplicate_rows_preserve_a_rank_tie():
    a = candidate(0, 20, 512)
    b = candidate(1, 20, 512)
    c = candidate(0, 20, 512 + model.ALIAS)
    d = candidate(1, 20, 512 + model.ALIAS)
    assert model.correspondent([a, b], [c, d]) == [(0, 0), (1, 1)]
    assert model.correspondent([a], [candidate(0, 21, 512)]) == []


def test_native_authority_mismatches_are_reported_with_the_terminal_record():
    left, right = factors([], 8), factors([], 7)
    left["clock_anchor"] = 7
    left["provenance"]["invalid_capture"] = [5]
    proof, _ = model.compare(left, right)
    assert proof["schema_and_clock_fields_changed"] == ["clock_anchor"]
    assert proof["exclusion_and_authority_fields_changed"] == ["invalid_capture"]
    assert not proof["probe_order_exact"]
    assert proof["unmatched_measured_probes"] == [(8, 0, 0, 0)]


def test_partial_comparison_ignores_uncommitted_visits_without_certifying_native_layout():
    native = factors([candidate(0, 10, 42)])
    native["delivery_clocks"] = [{"realtime_ns": 1000}, {"realtime_ns": 2000}]
    native["provenance"]["excluded_windows"] = [{"visit": 1}]
    visit = {
        "visit": 0,
        "status": "processed",
        "delivery_clock": {"realtime_ns": 1001},
        "clock_anchor": 1,
        "probes": native["source"]["probes"],
    }
    proof, _ = partial_parity([visit], native)
    assert proof["coverage"] == "closed_chunks_only"
    assert proof["delivery_clock_mismatches"] == [0]
    assert proof["first_clock_anchor_matches"]
    assert proof["visit_validity_changes"] == []
    assert proof["compared_visits"] == 1
    assert proof["archived_total_visits"] == 2
    assert "schema_and_clock_fields_changed" not in proof
