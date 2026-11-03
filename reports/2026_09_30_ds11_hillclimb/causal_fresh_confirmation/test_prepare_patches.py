from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("confirmation_prepare_patches", HERE / "prepare_patches.py")
prepare = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare
SPEC.loader.exec_module(prepare)


def proof_row(**changes):
    row = {
        "full_manifest_index": 75,
        "session": "scan-a",
        "capture_start_utc_ns": 300,
        "provider": "space-track",
        "snapshot_collected_utc_ns": 100,
        "snapshot_sha256": "sha256:" + "a" * 64,
        "archive_path": "/archive/a.tle",
        "journal_published_utc_ns": 200,
        "qualified": True,
    }
    row.update(changes)
    return row


def test_completion_proof_normalizes_exact_consumer_schema_and_strict_time():
    actual = prepare.normalize_proof(proof_row(), index=75, session="scan-a", capture_ns=300)
    assert actual == {
        "provider": "space-track",
        "collected_utc_ns": 100,
        "sha256": "a" * 64,
        "archive_path": "/archive/a.tle",
        "journal_published_utc_ns": 200,
        "qualified": True,
        "capture_start_utc_ns": 300,
    }
    for changes, match in (
        ({"qualified": False}, "binding"),
        ({"session": "other"}, "binding"),
        ({"journal_published_utc_ns": 300}, "pre-capture"),
        ({"journal_published_utc_ns": 99}, "pre-capture"),
    ):
        with pytest.raises(ValueError, match=match):
            prepare.normalize_proof(proof_row(**changes), index=75, session="scan-a", capture_ns=300)


def test_changed_slots_preserve_full_candidate_order_and_allow_empty():
    np.testing.assert_array_equal(
        prepare.changed_slots([9, 2, 7], [90, 20, 70], {20: {}, 90: {}}), [0, 1]
    )
    np.testing.assert_array_equal(
        prepare.changed_slots([9, 2, 7], [90, 20, 70], {10: {}}), []
    )
    with pytest.raises(ValueError, match="duplicate candidate"):
        prepare.changed_slots([1, 1], [10, 20], {10: {}})
    with pytest.raises(ValueError, match="duplicate physical"):
        prepare.changed_slots([1, 2], [10, 10], {10: {}})


def test_original_state_replay_enforces_position_and_velocity_tolerances():
    zeros = np.zeros((2, 3, 4, 3))
    assert prepare.replay_error(zeros, zeros, zeros, zeros) == (0.0, 0.0)
    with pytest.raises(ValueError, match="old-state replay failed"):
        prepare.replay_error(zeros + 1.1e-8, zeros, zeros, zeros)
    with pytest.raises(ValueError, match="old-state replay failed"):
        prepare.replay_error(zeros, zeros + 1.1e-10, zeros, zeros)
    bad = zeros.copy()
    bad.flat[0] = np.nan
    with pytest.raises(ValueError, match="nonfinite"):
        prepare.replay_error(bad, zeros, zeros, zeros)


def test_artifact_paths_require_exact_three_part_input():
    entry = {
        "artifacts": [
            {"kind": "observations", "path": "/x/observations.json"},
            {"kind": "candidates", "path": "/x/manifest.json"},
            {"kind": "candidates", "path": "/x/banks.npz"},
        ]
    }
    assert prepare.artifact_paths(entry) == (
        Path("/x/observations.json"), Path("/x/manifest.json"), Path("/x/banks.npz")
    )
    with pytest.raises(ValueError, match="cardinality"):
        prepare.artifact_paths({"artifacts": entry["artifacts"][:-1]})
