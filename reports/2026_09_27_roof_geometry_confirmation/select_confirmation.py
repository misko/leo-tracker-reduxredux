"""Freeze and cache a metadata-selected, disjoint roof confirmation cohort.

No reception, association, search, or location-result artifact is read here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import pickle
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = Path("/srv/bulk/leo")
POSE = ROOT / "capture-pose/gauss-r20-roof-20260926-v1"
DEVELOPMENT_MANIFEST = HERE.parent / "2026_09_27_roof_direction_subset/evaluation_manifest.json"
# Frozen before inspecting post-development readiness.  2026-09-27T05:14:10Z.
METADATA_CUTOFF_UTC_NS = 1790486050012766163


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_pose(pose: dict) -> None:
    body = {key: value for key, value in pose.items() if key != "binding_digest"}
    if digest(canonical(body)) != pose["binding_digest"]:
        raise ValueError("invalid pose binding digest")
    if digest(canonical(pose["pose_authority"])) != pose["pose_authority_digest"]:
        raise ValueError("invalid pose authority digest")
    authority = pose["pose_authority"]
    if not (authority["valid_from_utc_ns"] <= pose["capture_start_earliest_utc_ns"]
            and pose["capture_end_utc_ns"] <= authority["valid_until_utc_ns"]):
        raise ValueError("pose authority does not cover capture")


def select_earliest_ready(
    rows: list[dict], development_ids: set[str], after_utc_ns: int,
    cutoff_utc_ns: int, count: int = 4,
) -> tuple[list[dict], list[dict]]:
    """Select solely by disjointness, time, valid pose, and public readiness."""
    accounting = []
    eligible = []
    for row in sorted(rows, key=lambda item: (item["capture_start_utc_ns"], item["session_id"])):
        reasons = []
        if row["session_id"] in development_ids:
            reasons.append("development_cohort")
        if row["capture_start_utc_ns"] <= after_utc_ns:
            reasons.append("not_after_development")
        if row["capture_start_utc_ns"] > cutoff_utc_ns:
            reasons.append("after_metadata_cutoff")
        if not row["pose_valid"]:
            reasons.append("invalid_pose_binding")
        if not row["tracking_ready"]:
            reasons.append("tracking_analysis_not_ready")
        included = not reasons
        accounting.append({**row, "eligible": included, "exclusion_reasons": reasons})
        if included:
            eligible.append(row)
    selected = eligible[:count]
    if len(selected) != count:
        raise ValueError(f"only {len(selected)} eligible confirmation sessions; require {count}")
    return selected, accounting


def freeze(cutoff_utc_ns: int) -> None:
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

    target = HERE / "manifest.json"
    if target.exists():
        raise FileExistsError("confirmation manifest is already frozen")
    development = json.loads(DEVELOPMENT_MANIFEST.read_text())
    development_ids = {item["pose"]["session_id"] for item in development["sessions"]}
    after = max(item["pose"]["capture_start_earliest_utc_ns"] for item in development["sessions"])
    captures = AdaptiveHopIqStore(ROOT, read_only=True)
    analyses = AdaptiveHopAnalysisStore(ROOT, read_only=True)
    rows = []
    poses_by_id = {}
    try:
        for path in sorted(POSE.glob("*.json")):
            pose = json.loads(path.read_text())
            pose_valid = True
            pose_error = None
            try:
                validate_pose(pose)
                capture = captures.inspect(pose["session_id"])
                if capture.manifest_sha256 != pose["manifest_sha256"]:
                    raise ValueError("pose/capture manifest mismatch")
            except (KeyError, ValueError) as exc:
                pose_valid = False
                pose_error = str(exc)
                ready = False
            else:
                binding = bind_actual_visit_analysis(
                    capture.manifest.receipt,
                    input_manifest_sha256=capture.manifest_sha256,
                    probe_stride_ms=120,
                )
                with analyses.job(binding) as job:
                    ready = job.manifest() is not None
            poses_by_id[pose["session_id"]] = pose
            rows.append({
                "session_id": pose["session_id"],
                "capture_start_utc_ns": pose["capture_start_earliest_utc_ns"],
                "pose_valid": pose_valid,
                "pose_error": pose_error,
                "tracking_ready": ready,
            })
        selected, accounting = select_earliest_ready(
            rows, development_ids, after, cutoff_utc_ns, count=4
        )
        output = {
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "metadata_cutoff_utc_ns": cutoff_utc_ns,
            "selection": (
                "Earliest four complete public tracking analyses strictly after the final "
                "development capture, among valid pose-bound existing roof recordings at "
                "the frozen metadata cutoff; no reception or location products inspected."
            ),
            "development_session_ids": sorted(development_ids),
            "after_capture_start_utc_ns": after,
            "accounting": accounting,
            "sessions": [{"pose": poses_by_id[row["session_id"]], "split": "confirmation"}
                         for row in selected],
            "pose_limitations": (
                "Operator-supplied WGS84 roof coordinates; altitude and survey uncertainty "
                "were not supplied. Receiver mapping and orientation are provisional, RF "
                "phase centers and world tilt are unmeasured. This is not surveyed GPS truth."
            ),
            "candidate_policy": (
                "Future confirmation analysis must rebuild each full causal catalogue "
                "independently; no candidate list or fitted location from development is shared."
            ),
        }
        target.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    finally:
        captures.close()
        analyses.close()


def cache_inputs() -> None:
    from leo.storage import BundleNotFoundError
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    manifest = json.loads((HERE / "manifest.json").read_text())
    target = HERE / "inventory.json"
    if target.exists():
        raise FileExistsError("confirmation inventory is already frozen")
    output_dir = HERE / "cache"
    output_dir.mkdir(exist_ok=True)
    source = ScannerTrackingInputStore(ROOT)
    captures = AdaptiveHopIqStore(ROOT, read_only=True)
    inventory = []
    try:
        for item in manifest["sessions"]:
            pose = item["pose"]
            validate_pose(pose)
            capture = captures.inspect(pose["session_id"])
            if capture.manifest_sha256 != pose["manifest_sha256"]:
                raise ValueError("pose/capture mismatch during caching")
            entry = {
                "session_id": pose["session_id"], "split": "confirmation",
                "pose_verified": True, "input_manifest_sha256": capture.manifest_sha256,
                "capture_start_utc_ns": pose["capture_start_earliest_utc_ns"],
            }
            try:
                raw = source.load(pose["session_id"])
            except BundleNotFoundError as exc:
                entry.update(ready=False, reason=str(exc))
            else:
                if not raw.qualified or raw.input_manifest_sha256 != capture.manifest_sha256:
                    raise ValueError("unqualified or source-mismatched tracking input")
                probes = {(p.visit_index, p.probe_index, p.probe_start_ms, p.receiver_id): p
                          for p in raw.probes}
                if len(probes) != len(raw.probes):
                    raise ValueError("duplicate probes")
                expected = {event.visit_index for event in capture.manifest.receipt.events}
                if {p.visit_index for p in raw.probes} != expected:
                    raise ValueError("missing or unexpected visits")
                for probe in raw.probes:
                    other = probes.get((probe.visit_index, probe.probe_index,
                                        probe.probe_start_ms, 1 - probe.receiver_id))
                    if other is None or (probe.channel, probe.edge, probe.valid_start_counter) != (
                            other.channel, other.edge, other.valid_start_counter):
                        raise ValueError("missing or nonsimultaneous receiver counterpart")
                payload = pickle.dumps(raw, protocol=5)
                path = output_dir / f"{pose['session_id']}.pickle"
                if path.exists() and path.read_bytes() != payload:
                    raise ValueError("immutable local cache mismatch")
                if not path.exists():
                    path.write_bytes(payload)
                entry.update(
                    ready=True, visits=len(expected), probes=len(raw.probes),
                    sample_rate_hz=raw.sample_rate_hz,
                    analysis_manifest_sha256=raw.analysis_manifest_sha256,
                    cache_file=str(path), cache_sha256=digest(payload),
                )
            inventory.append(entry)
        target.write_text(json.dumps(inventory, indent=2, allow_nan=False) + "\n")
    finally:
        source.close()
        captures.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "cache"))
    parser.add_argument("--cutoff-utc-ns", type=int, default=METADATA_CUTOFF_UTC_NS)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.cutoff_utc_ns)
    else:
        cache_inputs()
