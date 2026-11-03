from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("causal_fresh_prepare", HERE / "prepare.py")
prepare = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare
SPEC.loader.exec_module(prepare)


def proof_row(**changes):
    row = {
        "index": 10,
        "session": "session-a",
        "capture_start_utc_ns": 2_000_000_000,
        "changed_candidate_count": 2,
        "provider": "space-track",
        "snapshot_collected_utc_ns": 1_000_000_000,
        "snapshot_sha256": "a" * 64,
        "archive_path": "/archive/a.tle",
        "journal_published_unix_s": 1.5,
        "qualified": True,
    }
    row.update(changes)
    return row


def scan_row():
    return {"index": 10, "session": "session-a", "start_utc_ns": 2_000_000_000}


def inventory_rows():
    return [
        {"changed": True, "selected_snapshot": "sha256:" + "a" * 64},
        {"changed": True, "selected_snapshot": "sha256:" + "a" * 64},
        {"changed": False, "selected_snapshot": "sha256:" + "b" * 64},
    ]


def test_completion_proof_requires_exact_qualified_pre_capture_snapshot():
    actual = prepare.validate_proof(proof_row(), scan_row(), inventory_rows())
    assert actual["journal_published_utc_ns"] == 1_500_000_000
    assert actual["qualified"] is True
    for changes, match in (
        ({"qualified": False}, "not qualified"),
        ({"session": "stale"}, "scan binding"),
        ({"journal_published_unix_s": 2.0}, "not published before"),
        ({"snapshot_sha256": "c" * 64}, "selected-snapshot"),
        ({"changed_candidate_count": 1}, "changed-candidate count"),
    ):
        with pytest.raises(ValueError, match=match):
            prepare.validate_proof(proof_row(**changes), scan_row(), inventory_rows())


def test_changed_slots_preserve_original_order_and_exact_record_membership():
    slots = prepare.changed_slots([8, 4, 6, 2], [80, 40, 60, 20], {60: {}, 80: {}})
    np.testing.assert_array_equal(slots, [0, 2])
    with pytest.raises(ValueError, match="shape"):
        prepare.changed_slots([1, 2], [10], {10: {}})
    with pytest.raises(ValueError, match="duplicate candidate"):
        prepare.changed_slots([1, 1], [10, 20], {10: {}})
    with pytest.raises(ValueError, match="duplicate physical"):
        prepare.changed_slots([1, 2], [10, 10], {10: {}})


def test_old_state_replay_enforces_both_exact_tolerances():
    zeros = np.zeros((1, 2, 3, 3))
    assert prepare.replay_error(zeros, zeros, zeros, zeros) == (0.0, 0.0)
    with pytest.raises(ValueError, match="old-state replay failed"):
        prepare.replay_error(zeros + 1.1e-8, zeros, zeros, zeros)
    with pytest.raises(ValueError, match="old-state replay failed"):
        prepare.replay_error(zeros, zeros + 1.1e-10, zeros, zeros)
    with pytest.raises(ValueError, match="shape mismatch"):
        prepare.replay_error(zeros[:, :1], zeros, zeros, zeros)
    invalid = zeros.copy()
    invalid.flat[0] = np.nan
    with pytest.raises(ValueError, match="nonfinite"):
        prepare.replay_error(invalid, zeros, zeros, zeros)
