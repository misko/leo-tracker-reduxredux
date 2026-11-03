import copy
import json
from pathlib import Path

import numpy as np

from tools.ds7_association_gate import (
    EXPECTED_SEED,
    EXPECTED_TAUS,
    _partition,
    audit,
    training_selection_digest,
)


def fixture(tmp_path: Path):
    session = "scan-fw-test"
    manifest = "sha256:" + "1" * 64
    visits = list(range(10, 16))
    mask = [_partition(session, visit) for visit in visits]
    while sum(mask) < 2 or sum(mask) == len(mask):
        visits = [value + 6 for value in visits]
        mask = [_partition(session, visit) for visit in visits]
    track = {
        "track_id": "sha256:" + "2" * 64,
        "times_s": list(map(float, range(6))),
        "measured_hz": list(map(float, range(6))),
        "training_mask": mask,
        "receiver_id": 0,
        "channel": 1,
        "rf_hz": 10_940_000_000.0,
        "visits": visits,
    }
    doc = {
        "schema": "ds7-baseline-track-export/v1",
        "session_id": session,
        "manifest_sha256": manifest,
        "partition_seed": EXPECTED_SEED,
        "tracks": [track],
    }
    plan = {"captures": [{"session_id": session, "manifest_sha256": manifest}]}
    tracks_path = tmp_path / "tracks.json"
    plan_path = tmp_path / "plan.json"
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    tracks_path.write_text(json.dumps(doc))
    plan_path.write_text(json.dumps(plan))
    ids = np.array([101, 202])
    shape = (2, 41, 6, 3)
    np.savez(
        bank_dir / "banks.npz",
        timing_grid_s=EXPECTED_TAUS,
        candidate_ids_0=ids,
        position_km_0=np.ones(shape),
        velocity_km_s_0=np.ones(shape),
    )
    shared = {
        "baseline_snapshot_sha256": "sha256:" + "3" * 64,
        "provider_sources": [],
        "catalogue_size": 1000,
    }
    (bank_dir / "shortlists.json").write_text(
        json.dumps(
            {
                "schema": "ds7-baseline-shortlists/v1",
                "session_id": session,
                "manifest_sha256": manifest,
                "minimum_anchor_top8_mass": 0.99,
                "shortlists": {track["track_id"]: ids.tolist()},
                **shared,
            }
        )
    )
    import hashlib

    digest = "sha256:" + hashlib.sha256(tracks_path.read_bytes()).hexdigest()
    (bank_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "ds7-baseline-bank-export/v1",
                "session_id": session,
                "manifest_sha256": manifest,
                "tracks_sha256": digest,
                "tracks": [
                    {"track_id": track["track_id"], "candidate_count": 2, "observation_count": 6}
                ],
                **shared,
            }
        )
    )
    return plan_path, tracks_path, bank_dir, doc


def test_gate_accepts_bound_training_only_bank(tmp_path):
    plan, tracks, bank, _ = fixture(tmp_path)
    assert audit(plan, tracks, bank)["status"] == "pass"


def test_held_values_cannot_change_training_selection_digest(tmp_path):
    _, _, _, doc = fixture(tmp_path)
    changed = copy.deepcopy(doc)
    for index, keep in enumerate(changed["tracks"][0]["training_mask"]):
        if not keep:
            changed["tracks"][0]["measured_hz"][index] += 1e9
    assert training_selection_digest(doc) == training_selection_digest(changed)


def test_physical_track_rf_cannot_change_canonical_selection_digest(tmp_path):
    _, _, _, doc = fixture(tmp_path)
    changed = copy.deepcopy(doc)
    changed["tracks"][0]["rf_hz"] = 99_000_000_000.0
    assert training_selection_digest(doc) == training_selection_digest(changed)


def test_gate_rejects_partition_leak_and_bank_membership_change(tmp_path):
    plan, tracks, bank, doc = fixture(tmp_path)
    doc["tracks"][0]["training_mask"][0] = not doc["tracks"][0]["training_mask"][0]
    tracks.write_text(json.dumps(doc))
    result = audit(plan, tracks, bank)
    assert result["status"] == "fail"
    assert any(
        "partition" in failure or "membership" in failure or "hash-bind" in failure
        for failure in result["failures"]
    )
