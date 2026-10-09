from pathlib import Path

import pytest
from sensitivity_policy import accepted, regional_path, source_stage


def test_seed_is_stage_priority_and_convergence_only():
    upstream = {
        "stages": {
            "drift-50": {"fitted-c": {"converged": False, "error_km": 0}},
            "post-200": {"fitted-c": {"converged": True, "error_km": 100}},
            "remove-5": {"fitted-c": {"converged": True, "error_km": 0}},
        }
    }
    assert source_stage(upstream) == "post-200"
    upstream["stages"]["drift-50"]["fitted-c"]["converged"] = True
    assert source_stage(upstream) == "drift-50"


def test_regional_receipt_preserves_retry_and_archive_provenance():
    result = {
        "upstream": {"regional_sources": {"fitted-c": "sep50"}},
        "member": {"inventory_label": "DS16-046"},
        "region_receipts": {"sep50": {"mode": "new_replay"}},
    }
    assert regional_path(result, "/r/retry/results/a.json", "/r") == Path(
        "/r/retry/regions/DS16-046/sep50.json"
    )
    result["region_receipts"]["sep50"] = {"mode": "archived", "path": "old/a.json"}
    assert regional_path(result, "/r/retry/results/a.json", "/r") == Path("/r/old/a.json")
    result["upstream"]["regional_sources"]["fitted-c"] = "baseline"
    assert regional_path(result, "/r/retry/results/a.json", "/r") is None


def test_no_qualified_seed_is_explicit_failure():
    with pytest.raises(ValueError, match="No qualified"):
        source_stage({"stages": {}})


def test_bad_fit_cannot_win_using_reference_error():
    bad = {"converged": False, "error_km": 0}
    good = {"converged": True, "error_km": 100}
    assert accepted(bad, good) is good
    assert accepted(good, bad) is good
