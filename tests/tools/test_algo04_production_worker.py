"""ALGO04 publication cannot bypass incumbent owners or sealed release bytes."""

import copy
import hashlib
import json
import runpy
from pathlib import Path

import pytest
import stage_algo04_release as staging
from algo04_production_worker import envelope


def incumbent():
    fixture = Path(__file__).resolve().parents[1] / "contracts/test_fast_graph_position_v2.py"
    return runpy.run_path(str(fixture))["terminal"]()


def test_qualified_candidate_retains_exact_incumbent_and_its_runtime():
    old = incumbent()
    saved = copy.deepcopy(old)
    result = envelope(old, copy.deepcopy(old), numerical_seconds=12.5)
    assert result["decision"] == "ALGO04_additive"
    assert result["total_seconds"] == old["total_seconds"] + 12.5
    assert result["incumbent"] == saved == old
    assert result["schema_version"] == 3


@pytest.mark.parametrize("failure", ["missing_candidate", "old_read_audit", "owner_change"])
def test_unqualified_update_retains_exact_published_position(failure):
    old = incumbent()
    candidate = copy.deepcopy(old)
    if failure == "missing_candidate":
        candidate = None
    elif failure == "old_read_audit":
        old["read_audit"]["verified"] = False
        old["decision"] = "ALGO02_fallback"
        old["selected"] = None
    else:
        candidate["selected"]["targets"][0]["norad"] = 3
        for arm in ("c0", "fitted_c"):
            candidate["selected"]["arms"][arm]["owners"]["new"] = 3
    result = envelope(old, candidate, numerical_seconds=4)
    assert result["decision"] == "ALGO03_fallback"
    assert result["position"] == old["position"]


def test_worker_cannot_publish_false_timing_or_missing_proof():
    old = incumbent()
    with pytest.raises(ValueError, match="runtime"):
        envelope(old, None, numerical_seconds=1200.1)
    candidate = copy.deepcopy(old)
    candidate["rf_checks"]["target_owners_verified"] = False
    with pytest.raises(ValueError, match="qualification"):
        envelope(old, candidate, numerical_seconds=10)


@pytest.mark.parametrize("corruption", [None, "manifest", "member", "unsafe"])
def test_stager_combines_frozen_v3_and_v4_members(monkeypatch, corruption):
    data = b"bounded numerical helper"
    name = "../escape.py" if corruption == "unsafe" else "tools/helper.py"
    manifest = json.dumps({"sha256": {name: hashlib.sha256(data).hexdigest()}}).encode()
    monkeypatch.setattr(staging, "MANIFEST_SHA256", hashlib.sha256(manifest).hexdigest())
    monkeypatch.setattr(
        staging.previous, "scientific_inventory", lambda *_: {"old.py": "old-digest"}
    )
    payloads = {staging.MANIFEST: manifest, name: data}
    if corruption == "manifest":
        payloads[staging.MANIFEST] = b"changed"
    if corruption == "member":
        payloads[name] = b"changed"
    monkeypatch.setattr(
        staging.previous, "_git", lambda source, *args: payloads[args[1].split(":", 1)[1]]
    )
    if corruption:
        with pytest.raises(ValueError):
            staging.scientific_inventory(Path("."), "a" * 40)
    else:
        result = staging.scientific_inventory(Path("."), "a" * 40)
        assert result["old.py"] == "old-digest"
        assert result[name] == hashlib.sha256(data).hexdigest()
