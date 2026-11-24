import copy
import gzip
import json

import pytest

from reports.ALGO08.v3 import history_risk_dense_mixed as trial
from reports.ALGO08.v3 import history_risk_dense_mixed_score as score


def test_complete_mixed_packet_checks_empty_rows_and_native_counts():
    probes = [{"candidates": [object()]} for _ in range(7336)] + [{"candidates": []} for _ in range(6194)]
    native = {"source": {"probes": probes, "raw_recording_authority_digest": "authority"},
              "clock_anchor": {"before": {"realtime_ns": 8}}, "provenance": {"processed_windows": 6765}}
    request = {"native": trial.NATIVE, "issued": 6772, "authority": "authority", "cutoff_utc_ns": 8}
    trial.certify_packet(native, request)
    probes[-1]["candidates"].append(object())
    with pytest.raises(ValueError, match="full-size"):
        trial.certify_packet(native, request)


def test_saved_witness_reports_actual_receiver_and_rejects_a_renderer_override():
    original = {"raw_route": "history_risk_installed", "solver_recipe": {"recipe": "live short receiver",
                "history_risk": {"requested": True}, "orbit_index": "cold"}, "evidence": {"grid": 179}}
    saved = trial.publication_witness(original)
    assert saved["solver_recipe"]["recipe"] == trial.RECIPE
    assert saved["raw_route"] == "history_risk_saved_mixed"
    assert saved["evidence"] == original["evidence"]
    assert original["solver_recipe"]["recipe"] == "live short receiver"
    original["solver_recipe"]["web_renderer"] = "Cairo"
    with pytest.raises(ValueError, match="ordinary renderer"):
        trial.publication_witness(original)


def test_additive_budget_requires_identically_bound_full_raw_receiver():
    with gzip.open(score.RAW_STAGE, "rb") as data:
        raw = json.load(data)
    binding = raw["binding"]
    request = {key: binding[key] for key in ("authority", "inventory", "session", "archive")}
    request.update(issued=6772, offer_sha256=binding["region_sha256"],
                   analysis_manifest=raw["candidate"]["recipe"]["receiver_audit"]["analysis_manifest"])
    result = score.additive_budget(raw, request, {"cpu_s": 30, "elapsed_s": 31}, {"cpu_ns": 0, "elapsed_ns": 1e9})
    assert result["measured_end_to_end"] is False
    assert result["sum_with_admission_elapsed_s"] == result["historical_acquire_elapsed_s"] + 32
    for field in ("analysis_manifest", "inventory", "offer_sha256", "authority"):
        wrong = dict(request, **{field: "different"})
        with pytest.raises(ValueError, match="ineligible"):
            score.additive_budget(raw, wrong, {"cpu_s": 30, "elapsed_s": 31}, {"cpu_ns": 0, "elapsed_ns": 0})
    wrong = copy.deepcopy(raw)
    wrong["candidate"]["recipe"]["receiver_audit"]["native"]["native_calls"]["short_primary"] -= 1
    with pytest.raises(ValueError, match="ineligible"):
        score.additive_budget(wrong, request, {"cpu_s": 30, "elapsed_s": 31}, {"cpu_ns": 0, "elapsed_ns": 0})


def test_media_compare_retains_byte_and_pixel_differences_independently():
    control = {name: {"size": [15, 20], "sha256": str(name), "rgba_sha256": str(name)} for name in range(8)}
    candidate = copy.deepcopy(control)
    candidate[2]["sha256"] += "changed"
    candidate[3]["rgba_sha256"] += "changed"
    shown = score.compare_media(control, candidate)
    assert shown[2] == {"size": True, "sha256": False, "rgba_sha256": True}
    assert shown[3] == {"size": True, "sha256": True, "rgba_sha256": False}
    with pytest.raises(ValueError, match="eight verified names"):
        score.compare_media(control, {name: row for name, row in candidate.items() if name != 3})
