"""Freeze the five metadata-selected confirmation exports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HILL = HERE.parent
FULL = HILL.parent / "2026_09_30_ds11_post_ds10/local/manifest.json"
ORIGINAL = HILL.parent / "2026_09_30_ds11_single10/plan.json"
INVENTORY = HILL / "remaining43_causal_inventory/inventory.json"
OUTPUT = HERE / "export-plan.json"
INDICES = (10, 18, 35, 60, 75)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    manifest = json.loads(FULL.read_text())
    inventory = json.loads(INVENTORY.read_text())
    original = json.loads(ORIGINAL.read_text())
    if manifest.get("dataset_id") != "DS11" or manifest.get("status") != "minted":
        raise ValueError("DS11 full manifest is not minted")
    if inventory.get("schema") != "ds11-remaining43-causal-orbit-inventory/v1":
        raise ValueError("remaining43 inventory schema mismatch")
    if inventory["summary"]["request_window_indices"] != list(INDICES):
        raise ValueError("inventory-selected membership mismatch")
    captures = []
    for index in INDICES:
        source = manifest["captures"][index]
        census = next(row for row in inventory["census"] if row["full_manifest_index"] == index)
        if (source["session_id"] != census["session"]
                or source["manifest_sha256"] != census["manifest_sha256"]
                or source["capture_start_utc_ns"] != census["capture_start_utc_ns"]):
            raise ValueError(f"inventory/full-manifest mismatch at {index}")
        captures.append({"full_manifest_index": index, **source})
    sources = [
        Path(__file__), HERE / "PROTOCOL.md", HERE / "export.py", FULL, ORIGINAL, INVENTORY,
        ROOT / "tools/ds7_export_baseline.py", ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
    ]
    result = {
        "schema": "ds11-causal-fresh-confirmation-export-plan/v1",
        "purpose": "metadata-selected causal-fresh confirmation; no position outcomes",
        "selection": "all remaining43 request-window indices; include shortlist no-ops",
        "count": len(captures),
        "captures": captures,
        "config": original["config"],
        "source_sha256": {str(path.resolve()): digest(path) for path in sources},
    }
    with OUTPUT.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"indices": list(INDICES), "inventory_sha256": digest(INVENTORY)}))


if __name__ == "__main__":
    main()
