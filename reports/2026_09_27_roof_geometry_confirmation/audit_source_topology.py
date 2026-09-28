"""Outcome-blind source-topology audit for calibration and confirmation inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import sys


HERE = Path(__file__).resolve().parent
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
LOCATION = HERE.parent / "2026_09_27_roof_location_geometry"
sys.path[:0] = [str(HERE), str(DIRECTION), str(LOCATION)]

import run_search as base
from source_links import resolve
from source_topology import filter_prepared


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def cohort() -> list[tuple[str, dict]]:
    development = json.loads((DIRECTION / "evaluation_inventory.json").read_text())
    frequency = json.loads((LOCATION / "fixedpoint_parameters.json").read_text())
    calibration = {row["session_id"]: row for row in development if row["split"] == "calibration"}
    if sorted(calibration) != frequency["calibration_sessions"] or len(calibration) != 6:
        raise ValueError("calibration cohort differs from frozen frequency model")
    confirmation = json.loads((HERE / "inventory.json").read_text())
    fresh = {row["session_id"]: row for row in confirmation}
    from run_confirmation import FROZEN_SESSION_IDS
    if set(fresh) != set(FROZEN_SESSION_IDS) or len(fresh) != 4:
        raise ValueError("confirmation inventory differs from frozen cohort")
    return ([('calibration', calibration[sid]) for sid in frequency["calibration_sessions"]]
            + [('confirmation', fresh[sid]) for sid in FROZEN_SESSION_IDS])


def main() -> None:
    target = HERE / "audit_source_topology.json"
    if target.exists():
        raise FileExistsError("source-topology audit is frozen; refusing overwrite")
    sessions = []
    for split, entry in cohort():
        sid = entry["session_id"]
        payload = Path(entry["cache_file"]).read_bytes()
        if not entry.get("ready") or digest(payload) != entry["cache_sha256"]:
            raise ValueError(f"{sid}: cache is not ready or digest-bound")
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
            "split": split,
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
        print("AUDIT", split, sid, receipt["counts"], flush=True)
    calibration = [row for row in sessions if row["split"] == "calibration"]
    output = {
        "scope": "exact six frozen frequency-calibration sessions plus four frozen confirmation sessions",
        "inputs": "digest-verified public TrackingInput and prepared tracks/source links only; no reception matching, GPS, search result, distance error, or prediction bank",
        "rule": sessions[0]["rule"],
        "calibration_zero_excluded": all(row["unchanged"] for row in calibration),
        "sessions": sessions,
        "source_code_sha256": {
            "source_topology.py": digest((HERE / "source_topology.py").read_bytes()),
            "source_links.py": digest((DIRECTION / "source_links.py").read_bytes()),
            "audit_source_topology.py": digest(Path(__file__).read_bytes()),
        },
    }
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    temporary.replace(target)


if __name__ == "__main__":
    main()
