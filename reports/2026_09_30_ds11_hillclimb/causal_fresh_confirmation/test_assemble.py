from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("causal_fresh_confirmation_assemble", HERE / "assemble.py")
assemble = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = assemble
SPEC.loader.exec_module(assemble)


def test_meaningful_intersection_preserves_exact_bank_slots_and_noop_tracks():
    changes = assemble.meaningful([
        {"norad": 10, "changed_sgp4_inputs": True, "original_epoch_ns": 1, "selected_epoch_ns": 2},
        {"norad": 20, "changed_sgp4_inputs": False, "original_epoch_ns": 1, "selected_epoch_ns": 2},
        {"norad": 30, "changed_sgp4_inputs": True, "original_epoch_ns": 2, "selected_epoch_ns": 2},
    ])
    assert set(changes) == {10}
    tracks = {
        "a": {"index": 0, "candidate_ids": [7, 8, 9], "candidate_norad": [30, 10, 40]},
        "b": {"index": 1, "candidate_ids": [1, 2], "candidate_norad": [50, 60]},
    }
    rows = assemble.intersect_tracks(tracks, changes, "capture_window")
    assert rows == [{
        "track_id": "a", "index": 0, "slots": [1], "candidate_ids": [8],
        "norads": [10], "kind": "capture_window",
    }]
