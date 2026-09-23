"""Independently bind the actual cached inputs used by the model experiments."""

import hashlib
import json
from pathlib import Path

from tools.research.position_dataset_split import load_partition


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    reports = root.parent
    manifest = reports / "2026_09_23_position_train_val_test/dataset/manifest.json"
    dataset = json.loads(manifest.read_text())
    train = load_partition(manifest, "training")
    validation = load_partition(manifest, "development_validation")
    inventory_path = reports / "2026_09_23_day_position_validation/inventory.json"
    assert "sha256:" + sha(inventory_path) == dataset["provenance"]["day_inventory_digest"]
    inventory = json.loads(inventory_path.read_text())
    authority = {r["session_id"]: r for r in inventory["scans"] if r.get("state") == "eligible"}
    cache_dirs = sorted(
        (reports / "2026_09_23_day_position_validation/replication").glob("block_*/cache")
    )
    cache_dirs.append(reports / "2026_09_23_sixteen_scan_comparison/joint/cache")
    index = {}
    for cache in cache_dirs:
        for scan in json.loads((cache / "cache_manifest.json").read_text())["scans"]:
            sid = scan["session_id"]
            if sid in index:
                raise ValueError("duplicate cache authority")
            index[sid] = cache
    rows = []
    for sid in (*train, *validation):
        cache = index[sid]
        evidence_path = cache / "evidence" / (sid + ".json")
        evidence = json.loads(evidence_path.read_text())
        assert evidence["session_id"] == sid
        digest = hashlib.sha256(
            json.dumps(evidence["tracks"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if sid in authority:
            assert digest == authority[sid]["evidence_digest"], "frozen track/mask mismatch"
        rows.append(
            {
                "session_id": sid,
                "partition": "training" if sid in train else "retrospective_validation",
                "cache_manifest_sha256": sha(cache / "cache_manifest.json"),
                "evidence_sha256": sha(evidence_path),
                "track_evidence_digest": digest,
                "numerical_state_npz_sha256": sha(cache / "scans" / (sid + ".npz")),
                "day_inventory_evidence_compared": sid in authority,
            }
        )
    result = {
        "dataset_sha256": sha(manifest),
        "audit_source_sha256": sha(Path(__file__)),
        "training_scans": len(train),
        "validation_scans": len(validation),
        "prospective_test_inputs_opened": False,
        "note": (
            "NPZ hashes bind current numerical inputs; they are not a fresh propagation "
            "verification. Original-16 evidence is bound by file hash; day evidence is also "
            "compared to its frozen inventory."
        ),
        "scans": rows,
    }
    (root / "input_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Bound {len(rows)} cached recordings; day track/mask comparisons all pass.")


if __name__ == "__main__":
    main()
