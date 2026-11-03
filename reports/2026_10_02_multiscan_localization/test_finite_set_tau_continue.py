import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from finite_set_tau_continue import (
    assert_inherited_hashes_unchanged,
    validate_bound_input_hashes,
    validate_geometry_binding,
    validate_source_record,
)


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source():
    bank = [1, 2]
    trial = {"satellite_indices": bank, "success": True}
    attempt = {
        "satellite_indices": bank,
        "profile": {"complete": True},
        "local_refinement": {"success": True},
    }
    return {
        "schema": "finite-set-tau-profile/v1",
        "run_id": "finite-set-tau-profile-v1",
        "unit": {"unit_id": "DS10-S01", "session_ids": ["scan-a"]},
        "dataset": "DS10",
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed_utc": "2026-10-02T00:00:00+00:00",
        "source_fit_sha256": "b" * 64,
        "source_hashes": {"/input": "a" * 64},
        "fit": {
            "full_bank": bank,
            "trials": [trial],
            "attempts": [attempt],
            "all_timing_profiles_complete": True,
            "local_refinements_resolved": True,
            "selection": {"selection_resolved": True},
        },
    }


def test_source_validation_accepts_only_complete_truth_free_sealed_result():
    source = _source()
    assert validate_source_record(source, "DS10-S01") is source

    mutations = (
        ("schema", "wrong"),
        ("reference_read_before_seal", True),
        ("evaluation_written", True),
        ("sealed_utc", None),
    )
    for key, value in mutations:
        changed = copy.deepcopy(source)
        changed[key] = value
        with pytest.raises(ValueError):
            validate_source_record(changed, "DS10-S01")


def test_source_validation_rejects_incomplete_or_unconverged_bank():
    source = _source()
    source["fit"]["attempts"][0]["profile"]["complete"] = False
    with pytest.raises(ValueError, match="complete profile"):
        validate_source_record(source, "DS10-S01")

    source = _source()
    source["fit"]["attempts"][0]["local_refinement"]["success"] = False
    with pytest.raises(ValueError, match="complete profile"):
        validate_source_record(source, "DS10-S01")


def test_inherited_hash_validation_detects_changed_source_file(tmp_path):
    path = tmp_path / "dependency.py"
    path.write_text("sealed\n")
    snapshot = {str(path.resolve()): _hash(path)}
    assert assert_inherited_hashes_unchanged(snapshot) == snapshot

    path.write_text("changed\n")
    with pytest.raises(RuntimeError, match="provenance changed"):
        assert_inherited_hashes_unchanged(snapshot)


def test_bound_input_validation_requires_exact_paths_and_hashes(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.npz"
    first.write_text("first")
    second.write_bytes(b"second")
    expected = {
        str(first.resolve()): _hash(first),
        str(second.resolve()): _hash(second),
    }
    assert validate_bound_input_hashes((first, second), expected) == expected

    with pytest.raises(ValueError, match="loader inputs differ"):
        validate_bound_input_hashes((first,), expected)

    second.write_bytes(b"modified")
    with pytest.raises(ValueError, match="loader inputs differ"):
        validate_bound_input_hashes((first, second), expected)


def test_geometry_binding_canonicalizes_arrays_and_rejects_mismatch(tmp_path):
    grouped = tmp_path / "fit.json"
    grouped.write_text(json.dumps({"fit": {"grouped_geometry": {"rows": [1, 2]}}}))
    source = _source()
    source["source_fit_sha256"] = _hash(grouped)
    source["source_hashes"] = {str(grouped.resolve()): _hash(grouped)}
    assert validate_geometry_binding(
        source,
        {"rows": np.array([1, 2])},
        source_path=grouped,
    ) == {"rows": [1, 2]}

    with pytest.raises(ValueError, match="grouped geometry differs"):
        validate_geometry_binding(source, {"rows": [2, 1]}, source_path=grouped)
