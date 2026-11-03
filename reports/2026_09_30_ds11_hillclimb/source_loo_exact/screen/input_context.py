"""Digest-bound original DS11 screen input loader without the phase-one index limit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
HILL = HERE.parents[1]
ROOT = HERE.parents[3]
BASE = HILL.parent / "2026_09_30_ds11_single10"
SCREEN = (0, 4, 8, 12, 16, 20, 24, 28)

sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_scan(index):
    """Return validated plan, one loaded document, and candidate physical IDs."""
    if index not in SCREEN:
        raise ValueError(f"screen input index must be one of {SCREEN}")
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    entry = plan["inputs"][index]
    for artifact in entry["artifacts"]:
        if artifact["sha256"] != "sha256:" + digest(artifact["path"]):
            raise ValueError(f"input artifact binding mismatch: {artifact['path']}")
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    if len(documents) != 1 or documents[0]["session_id"] != entry["session_id"]:
        raise ValueError("loaded document session mismatch")

    sidecar_path = HILL / "source_balance" / "catalogue_identities.json"
    sidecar = json.loads(sidecar_path.read_text())
    if sidecar.get("schema") != "ds11-source-balance-identities/v1":
        raise ValueError("identity sidecar schema mismatch")
    if sidecar.get("plan_sha256") != digest(plan_path):
        raise ValueError("identity sidecar plan binding mismatch")
    scan = sidecar["scans"][str(index)]
    if scan["session_id"] != entry["session_id"]:
        raise ValueError("identity sidecar session mismatch")
    artifact_paths = [Path(item["path"]) for item in entry["artifacts"]]
    bindings = {
        "observation_sha256": next(path for path in artifact_paths if path.name == "observations.json"),
        "manifest_sha256": next(path for path in artifact_paths if path.name == "manifest.json"),
        "bank_sha256": next(path for path in artifact_paths if path.suffix == ".npz"),
    }
    for key, path in bindings.items():
        if scan[key] != digest(path):
            raise ValueError(f"identity sidecar {key} mismatch")
    candidate_norad = [{
        track_id: row["candidate_norad"] for track_id, row in scan["tracks"].items()
    }]
    document_ids = {track["track_id"] for track in documents[0]["tracks"]}
    if set(candidate_norad[0]) != document_ids:
        raise ValueError("identity sidecar and loaded track roster differ")
    for track in documents[0]["tracks"]:
        if len(candidate_norad[0][track["track_id"]]) != track["candidate_position_km"].shape[0]:
            raise ValueError("identity sidecar candidate count mismatch")
    return plan_path, plan, entry, documents, sidecar_path, candidate_norad
