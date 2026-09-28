"""Outcome-blind source-topology audit for the second confirmation cohort."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import sys


HERE = Path(__file__).resolve().parent
FIRST = HERE.parent / "2026_09_27_roof_geometry_confirmation"
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
LOCATION = HERE.parent / "2026_09_27_roof_location_geometry"
sys.path[:0] = [str(FIRST), str(DIRECTION), str(LOCATION)]

import run_search as base
from source_links import resolve
from source_topology import filter_prepared


SESSION_IDS = (
    "scan-fw-339af454a2aab2f4",
    "scan-fw-53ce822d78d476ba",
    "scan-fw-e76c229e9dc498b3",
    "scan-fw-c9db23377d1194dd",
)


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def main() -> None:
    target = HERE / "audit_source_topology.json"
    if target.exists():
        raise FileExistsError("balanced topology audit exists; refusing overwrite")
    manifest_bytes = (HERE / "manifest.json").read_bytes()
    inventory_bytes = (HERE / "inventory.json").read_bytes()
    inventory = json.loads(inventory_bytes)
    by_id = {entry["session_id"]: entry for entry in inventory}
    if len(by_id) != 4 or set(by_id) != set(SESSION_IDS):
        raise ValueError("inventory differs from frozen second cohort")
    parent_audit_path = FIRST / "audit_source_topology.json"
    parent_audit_bytes = parent_audit_path.read_bytes()
    parent_audit = json.loads(parent_audit_bytes)
    if len([row for row in parent_audit["sessions"] if row["split"] == "calibration"]) != 6:
        raise ValueError("parent calibration topology audit is incomplete")
    sessions = []
    for sid in SESSION_IDS:
        entry = by_id[sid]
        payload = Path(entry["cache_file"]).read_bytes()
        if (not entry.get("ready") or not entry.get("pose_verified") or
                digest(payload) != entry["cache_sha256"]):
            raise ValueError(f"{sid}: invalid frozen cache")
        raw = pickle.loads(payload)
        if raw.session_id != sid or raw.input_manifest_sha256 != entry["input_manifest_sha256"]:
            raise ValueError(f"{sid}: cached public input identity mismatch")
        prepared = base.prepare_adaptive_tle_position_inputs(
            sid, inputs=base.CachedInput(raw),
            archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
        if (prepared.input_manifest_sha256 != entry["input_manifest_sha256"] or
                prepared.analysis_manifest_sha256 != entry["analysis_manifest_sha256"]):
            raise ValueError(f"{sid}: prepared public input digest mismatch")
        links = resolve(raw)
        filtered, receipt = filter_prepared(prepared, links)
        sessions.append({
            "session_id": sid,
            "split": "balanced_confirmation",
            "cache_sha256": entry["cache_sha256"],
            "input_manifest_sha256": prepared.input_manifest_sha256,
            "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
            "evidence_sha256": prepared.evidence_sha256,
            "snapshot_digest": prepared.snapshot_digest,
            "source_links_sha256": digest(canonical(links)),
            "source_link_records": len(links),
            "filter_returns_same_object": filtered is prepared,
            **receipt,
        })
        print("AUDIT", sid, receipt["counts"], flush=True)
    output = {
        "scope": "four frozen second-confirmation sessions only",
        "inputs": "digest-verified public TrackingInput and prepared tracks/source links only; no reception matching, GPS, search result, distance error, or prediction bank",
        "rule": sessions[0]["rule"],
        "manifest_sha256": digest(manifest_bytes),
        "inventory_sha256": digest(inventory_bytes),
        "parent_calibration_topology_audit_sha256": digest(parent_audit_bytes),
        "parent_calibration_binding": "The six-session calibration audit is bound separately and is not recomputed or combined into this confirmation audit.",
        "sessions": sessions,
        "source_code_sha256": {
            "source_topology.py": digest((FIRST / "source_topology.py").read_bytes()),
            "source_links.py": digest((DIRECTION / "source_links.py").read_bytes()),
            "audit_source_topology.py": digest(Path(__file__).read_bytes()),
        },
    }
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    temporary.replace(target)


if __name__ == "__main__":
    main()
