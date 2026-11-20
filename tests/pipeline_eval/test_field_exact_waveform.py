import json
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.qualification import field_exact_waveform as trial
from tools.pipeline_eval.qualification import field_exact_waveform_results as results
from tools.pipeline_eval.variants.prepared_hotpath_peaks import retained_peaks


def public_native():
    candidate = {
        "candidate_rank": 2,
        "integer_epoch_sample": 111,
        "fractional_epoch_offset_samples": 0.0,
        "fractional_tracking_cfo_hz": 135.0,
        "fractional_exact_score": 0.031,
        "fractional_control_score": 0.003,
        "fractional_margin": results.MARGIN_GATE,
        results.GATE: True,
    }
    probes = [
        dict(visit_index=1, receiver_id=0, candidates=[candidate]),
        dict(visit_index=1, receiver_id=1, candidates=[]),
    ]
    return dict(
        schema_version=2,
        clock_anchor={"counter": 1},
        delivery_clocks=[{"capture_counter": 5, "delivery_ns": 7}],
        last_sample_counter=8,
        source=dict(probes=probes, input_manifest_sha256="capture"),
        provenance=dict.fromkeys(results.PROVENANCE_FIELDS),
    )


def test_exact_public_encoding_checks_all_fields_and_preserves_a_miss():
    archived = public_native()
    current = deepcopy(archived)
    compared = results.parity(current, archived)
    assert compared["classification"] == "exact"
    assert compared["exact"] == {"probes": 2, "candidates": 1}
    assert compared["counts"]["fresh"]["empty_probes"] == 1
    assert compared["counts"]["fresh"]["gate_formula_errors"] == 0
    assert set(compared["per_candidate_field"]) == set(results.CANDIDATE_FIELDS)
    assert not any(compared["per_candidate_field"].values())


@pytest.mark.parametrize("field", results.NUMERIC)
def test_single_numeric_change_disqualifies_when_gate_is_preserved(field):
    archived = public_native()
    current = deepcopy(archived)
    changed = current["source"]["probes"][0]["candidates"][0]
    changed[field] += 1
    compared = results.parity(current, archived)
    assert compared["classification"] == "numeric_difference"
    assert compared["per_candidate_field"][field] == 1
    assert compared["max_absolute_numeric_delta"][field] == pytest.approx(1)
    assert not any(compared["gate_equivalence"].values())


def test_signed_zero_order_mask_exclusion_and_clock_have_independent_audits():
    archived = public_native()
    current = deepcopy(archived)
    current["source"]["probes"][0]["candidates"][0]["fractional_epoch_offset_samples"] = -0.0
    assert results.parity(current, archived)["classification"] == "numeric_difference"
    current = deepcopy(archived)
    current["source"]["probes"][0]["candidates"].clear()
    current["source"]["probes"].reverse()
    current["delivery_clocks"][0]["delivery_ns"] += 1
    current["provenance"]["excluded_windows"] = [{"visit": 2}]
    comparison = results.parity(current, archived)
    assert comparison["classification"] == "support_or_gate_difference"
    assert comparison["delivery_clock_rows_differ"] == 1
    assert not comparison["probe_order_exact"]
    assert not comparison["capture_validity_fields_exact"]["excluded_windows"]
    assert comparison["rank_masks"]["differing_empty_probes"] == 1
    assert comparison["gate_equivalence"]["differing_gate_masks"] == 1


def test_gate_flag_and_formula_audits_disqualify_a_stale_pass_flag():
    archived = public_native()
    current = deepcopy(archived)
    current["source"]["probes"][0]["candidates"][0][results.GATE] = False
    comparison = results.parity(current, archived)
    assert comparison["classification"] == "support_or_gate_difference"
    assert comparison["per_candidate_field"][results.GATE] == 1
    assert comparison["counts"]["fresh"]["gate_formula_errors"] == 1
    assert comparison["gate_equivalence"]["differing_positive_probes"] == 1


def test_raw_adapter_scopes_row_selector_and_pruned_fine_to_existing_worker(monkeypatch, tmp_path):
    original = acquisition._retain_score_map_peaks
    source = Path(acquisition.__file__)
    lock = dict(producer=str(source.parents[2]), sources={str(source): "signed"})
    library = tmp_path / "fine.so"
    monkeypatch.setattr(trial.base, "configure", lambda _: (lock, {"fine": library}))
    opened = set()

    class FakeSearch:
        compatible = True

        def __init__(self, shared_library, producer):
            assert shared_library == library and producer is acquisition

        @contextmanager
        def route(self):
            opened.add("pruned")
            try:
                yield
            finally:
                opened.remove("pruned")

    def worker(work, cpu):
        assert work == tmp_path and cpu == 4
        assert opened == {"pruned"}
        assert acquisition._retain_score_map_peaks is retained_peaks
        raise RuntimeError("bounded worker interrupted")

    monkeypatch.setattr(trial, "FineSearch", FakeSearch)
    monkeypatch.setattr(trial.prepared, "raw", worker)
    with pytest.raises(RuntimeError, match="bounded worker interrupted"):
        trial.raw(tmp_path, 4)
    assert not opened
    assert acquisition._retain_score_map_peaks is original


def test_timing_boundary_and_fine_telemetry_preserve_censored_visits(tmp_path):
    samples = [
        dict(visit=1, status="processed", cpu_ms=7, wall_ms=20),
        dict(visit=2, status="processed", cpu_ms=11, wall_ms=77),
        dict(visit=3, status="invalid_capture", cpu_ms=0, wall_ms=0),
    ]
    metric = results.timing_stats(samples)
    assert metric["wall_ms"]["within_20"] == 1
    assert metric["wall_ms"]["worst"] == [{"visit": 2, "ms": 77.0}, {"visit": 1, "ms": 20.0}]
    assert metric["cpu_ms"]["total_cpu_s"] == pytest.approx(0.018)
    grid = [dict(r, cpu=4, ordinal=i) for i, r in enumerate(samples)]
    log = tmp_path / "cpu-4.log"
    fine = [
        dict(ordinal=i, calls=c, fallbacks=f, frames=c * 14, bins=c * 100, workspace_bytes=1024)
        for i, (c, f) in enumerate(((2, 0), (1, 1), (0, 0)))
    ]
    log.write_text("".join(trial.TRACE + json.dumps(r) + "\n" for r in fine))
    receipt = results.fine_telemetry(tmp_path, grid, {"workers": [(4, 2, [])]})
    assert [r["fallbacks"] for r in receipt] == [0, 1, 0]
    assert receipt[-1]["status"] == "invalid_capture"
