import copy

import pytest

from tools.pipeline_eval.qualification.consistent_peaks_results import (
    observed_factor,
    physical_audit,
)
from tools.pipeline_eval.variants import consistent_peaks as trial


def candidate(rank, epoch, cfo, *, gate=True, margin=10):
    return {
        trial.GATE: gate,
        trial.CFO: cfo,
        "candidate_rank": rank,
        "fractional_margin": margin,
        "integer_epoch_sample": epoch,
        "fractional_epoch_offset_samples": 0.125,
    }


def window(visit):
    return {
        "visit_index": visit,
        "receiver_id": 0,
        "channel": 3,
        "edge": "upper",
        "actual_rf_hz": 11_325_000_000 + visit * 7000,
        "valid_start_counter": 12_000_000_000_000 + 4_000_000 * visit,
        "probe_start_ms": 0,
        "candidates": [candidate(1, 10, 1_000 - 7000 * visit)],
    }


def fixture(old_epoch=40, old_cfo=None):
    document = {
        "source": {
            "sample_rate_hz": 10_000_000,
            "probe_ms": 20,
            "probes": [window(visit) for visit in range(5)],
        },
        "provenance": {"run_id": "fixture"},
    }
    probes = document["source"]["probes"]
    middle = probes[2]["candidates"]
    cfo = middle[0][trial.CFO]
    middle[:] = [
        candidate(1, old_epoch, cfo if old_cfo is None else old_cfo, margin=20),
        candidate(2, 42, cfo, margin=11),
        candidate(3, 10, cfo),
        candidate(4, 11, cfo, gate=False, margin=100),
        candidate(5, 54, cfo, margin=9),
    ]
    return document, probes


def test_repair_requires_both_sides_and_retains_untouched_payload():
    document, probes = fixture()
    edits, counts = trial.select(document)
    assert edits == [
        {
            "index": 2,
            "visit": 2,
            "receiver": 0,
            "old_winner": 0,
            "new_winner": 2,
            "removed": [0, 1],
            "anchors": [0, 1, 3, 4],
            "future_samples": 8_000_000,
        }
    ]
    assert counts["withheld_candidates"] == 2
    assert counts["positive"] == 5
    out = trial.apply(document, edits, "sha256:" + "1" * 64)
    updated = out["source"]["probes"]
    assert len(probes[2]["candidates"]) == 5
    assert updated[2]["candidates"] == probes[2]["candidates"][2:]
    assert all(
        a is b for a, b in zip(probes[2]["candidates"][2:], updated[2]["candidates"], strict=True)
    )
    assert all(updated[i] is probes[i] for i in (0, 1, 3, 4))


def test_abstains_without_nonrecursive_support_or_a_unique_alternate():
    document, probes = fixture()
    probes[4]["candidates"].clear()
    edits, counts = trial.select(document)
    assert edits == [] and counts["incomplete_anchors"] == 1
    assert trial.apply(document, edits, None) is document
    document, probes = fixture()
    probes[2]["candidates"][1]["integer_epoch_sample"] = 10
    edits, counts = trial.select(document)
    assert edits == [] and counts["ambiguous_alternate"] == 1


def test_wrapped_timing_cannot_admit_an_absolute_cfo_alias():
    document, _ = fixture(old_epoch=10, old_cfo=227_272 - 13_000)
    edits, counts = trial.select(document)
    assert edits[0]["new_winner"] == 2 and counts["changed_winners"] == 1
    document, _ = fixture(old_epoch=10)
    edits, counts = trial.select(document)
    assert edits == [] and counts["winner_supported"] == 1


def test_physical_audit_distinguishes_admitted_hidden_peak_and_unsupported_target():
    stock, _ = fixture()
    stock.update(clock_anchor=1, delivery_clocks=[], last_sample_counter=20)
    original = copy.deepcopy(stock)
    probes = original["source"]["probes"]
    probes[2]["candidates"] = [probes[2]["candidates"][2]]
    probes[4]["candidates"][0][trial.CFO] += 1_000_000
    edits, _ = trial.select(stock)
    candidate = trial.apply(stock, edits, "sha256:" + "1" * 64)
    counts, changed = physical_audit(original, stock, candidate, edits)
    assert counts["original_winners"] == 5
    assert counts["retained_original"] == 3
    assert counts["latent_gated_original"] == 1
    assert counts["original_recovered"] == 1
    assert counts["original_lost"] == 0
    assert counts["other_cfo"] == 1
    assert changed[0]["matched_after"] is True
    candidate = copy.deepcopy(candidate)
    candidate["source"]["probes"][2]["candidates"][0]["fractional_margin"] += 1
    with pytest.raises(ValueError, match="changed a native candidate score"):
        physical_audit(original, stock, candidate, edits)


def test_exact_noop_audit_uses_authenticated_stock_without_worker_scratch(tmp_path):
    stock, _ = fixture()
    receipt = {"id": "fixture", "native_sha256": "a" * 64, "stock_native_sha256": "a" * 64}
    assert observed_factor(tmp_path, receipt, stock, []) is stock
    receipt["native_sha256"] = "b" * 64
    with pytest.raises(FileNotFoundError):
        observed_factor(tmp_path, receipt, stock, [])
