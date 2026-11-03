"""Read-only metadata inventory of every on-disk eight-channel fast recording.

Run with read permission for source roots. Writes only the explicitly supplied
output directory. IQ stays in place; its recorded hashes are pinned, not rehashed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def read_json(path):
    raw = path.read_bytes()
    return json.loads(raw), digest(raw)


def channels(configuration):
    return sorted(
        {
            t.get("channel")
            for t in configuration.get("targets", [])
            if isinstance(t.get("channel"), int)
        }
    )


def group_identity(segments):
    """Deduplicate raw content independently of names and metadata wrappers."""
    content = sorted(
        (c["compressed_sha256"], c["index_sha256"])
        for s in segments
        for c in s["document"].get("chunks", [])
    )
    return digest(json.dumps(content, separators=(",", ":")).encode())


def inventory(
    roots,
    analysis_root,
    cutoff_ns,
    *,
    start_ns=0,
    dataset_id="DS20",
    required_channels=tuple(range(1, 9)),
):
    groups = defaultdict(list)
    errors = []
    checked = set()
    for root in roots:
        for path in sorted(root.rglob("manifest.json")):
            if path in checked:
                continue
            checked.add(path)
            try:
                document, sha = read_json(path)
            except (ValueError, OSError) as error:
                errors.append({"path": str(path), "error": str(error)})
                continue
            if document.get("kind") != "short_window_iq_recording":
                continue
            if document.get("created_utc_ns", cutoff_ns + 1) > cutoff_ns:
                continue
            groups[path.parent.parent].append(
                {"path": str(path), "sha256": sha, "document": document}
            )
    source_inputs = defaultdict(list)
    for path in sorted((analysis_root / "fast-scan-inputs").glob("*.json")):
        d, sha = read_json(path)
        source_inputs[d["recording_name"]].append(
            {
                "path": str(path),
                "sha256": sha,
                "session_id": path.stem,
                "window_count": d.get("window_count"),
                "segments": d.get("segments", []),
            }
        )
    tracking_inputs = defaultdict(list)
    for path in sorted((analysis_root / "fast-scan-tracking-inputs").glob("*.json")):
        d, sha = read_json(path)
        source = d["source"]
        tracking_inputs[source["session_id"]].append(
            {
                "path": str(path),
                "sha256": sha,
                "raw_recording_authority_digest": source.get("raw_recording_authority_digest"),
                "input_manifest_sha256": source.get("input_manifest_sha256"),
                "capture_start_utc_ns": source.get("capture_start_utc_ns"),
                "capture_end_utc_ns": source.get("capture_end_utc_ns"),
            }
        )
    jobs = {}
    for path in sorted((analysis_root / "fast-scan-automatic").glob("*.json")):
        d, sha = read_json(path)
        jobs[d["recording_id"]] = {"path": str(path), "sha256": sha, "document": d}
    unique = {}
    excluded = []
    for recording_root, segments in sorted(groups.items()):
        # Select whole acquisitions by their earliest segment, never slice an
        # acquisition that began before the parent boundary.
        if min(s["document"]["created_utc_ns"] for s in segments) < start_ns:
            continue
        configured = sorted(
            {c for s in segments for c in channels(s["document"].get("configuration", {}))}
        )
        if required_channels is not None and configured != list(required_channels):
            excluded.append(
                {
                    "recording_id": recording_root.name,
                    "path": str(recording_root),
                    "reason": "configuration_does_not_cover_channels_1_to_8",
                    "channels": configured,
                }
            )
            continue
        identity = group_identity(segments)
        if identity in unique:
            unique[identity]["raw_recording"]["duplicate_roots"].append(str(recording_root))
            continue
        segments.sort(key=lambda s: s["document"]["created_utc_ns"])
        chunks = []
        observed = set()
        integrity_errors = []
        for segment in segments:
            directory = Path(segment["path"]).parent
            for chunk in segment["document"].get("chunks", []):
                item = dict(chunk, segment_manifest=segment["path"])
                index = directory / chunk["index_relative_path"]
                payload = directory / chunk["payload_relative_path"]
                item.update(index_path=str(index), payload_path=str(payload))
                try:
                    raw = index.read_bytes()
                    item["observed_index_sha256"] = digest(raw)
                    observed.update(int(c) for c in re.findall(rb'"channel"\s*:\s*(\d+)', raw))
                    observed.update(
                        int(c) for c in re.findall(rb'"target_id"\s*:\s*"ch(\d+)-', raw)
                    )
                    if item["observed_index_sha256"] != chunk["index_sha256"]:
                        integrity_errors.append(f"index digest mismatch: {index}")
                    item["observed_payload_bytes"] = payload.stat().st_size
                    if item["observed_payload_bytes"] != chunk["compressed_bytes"]:
                        integrity_errors.append(f"payload size mismatch: {payload}")
                except OSError as error:
                    integrity_errors.append(str(error))
                chunks.append(item)
        name = recording_root.name
        inputs = source_inputs.get(name, [])
        sessions = sorted({i["session_id"] for i in inputs})
        job = jobs.get(name)
        if job and job["document"].get("session_id"):
            sessions = sorted(set(sessions + [job["document"]["session_id"]]))
        tracking = [i for session in sessions for i in tracking_inputs.get(session, [])]
        complete = all(s["document"].get("status") == "complete" for s in segments)
        unique[identity] = {
            "case_id": name + "-" + identity[-12:],
            "recording_id": name,
            "channels": configured,
            "observed_channels": sorted(observed),
            "session_id": (job or {}).get("document", {}).get("session_id")
            or next(iter(sessions), None),
            "session_ids": sessions,
            "recording_state": "complete" if complete else "incomplete",
            "captured_utc_ns": segments[0]["document"]["created_utc_ns"],
            "window_count": sum(s["document"].get("window_count", 0) for s in segments),
            "source_inputs": inputs,
            "tracking_inputs": tracking,
            "automatic_job": job,
            "raw_authority_digest": next(
                (t["raw_recording_authority_digest"] for t in tracking), None
            ),
            "raw_recording": {
                "identity_sha256": identity,
                "root": str(recording_root),
                "duplicate_roots": [],
                "segments": segments,
                "chunks": chunks,
                "integrity_errors": integrity_errors,
                "iq_hash_verification": "manifest_hashes_pinned_payload_sizes_checked_not_rehashed",
            },
        }
    members = sorted(unique.values(), key=lambda m: (m["captured_utc_ns"], m["recording_id"]))
    orphan_inputs = [
        dict(recording_id=name, source_inputs=items)
        for name, items in source_inputs.items()
        if name not in {m["recording_id"] for m in members}
    ]
    return {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "start_utc_ns": start_ns,
        "cutoff_utc_ns": cutoff_ns,
        "cutoff_utc": datetime.fromtimestamp(cutoff_ns / 1e9, UTC).isoformat(),
        "selection": (
            "all discovered fast raw recordings configured for channels 1..8 before cutoff; "
            "incomplete recordings retained; no analysis-readiness gate"
        ),
        "discovery_roots": [str(r) for r in roots],
        "members": members,
        "excluded": excluded,
        "discovery_errors": errors,
        "orphan_analysis_inputs": orphan_inputs,
        "counts": {
            "members": len(members),
            "complete": sum(m["recording_state"] == "complete" for m in members),
            "incomplete": sum(m["recording_state"] != "complete" for m in members),
            "with_tracking_input": sum(bool(m["tracking_inputs"]) for m in members),
            "raw_group_roots": len(groups),
            "excluded_roots": len(excluded),
        },
    }


def qualify_existing(output, analysis_root):
    """Freeze broad inventory, then apply the user's GLRT evidence requirement."""
    manifest = output / "manifest.json"
    broad = output / "all-configured-eight-channel-inventory.json"
    if not broad.exists():
        raw = manifest.read_bytes()
        broad.write_bytes(raw)
        broad.with_suffix(".sha256").write_text(digest(raw) + "  " + broad.name + "\n")
    result = json.loads(broad.read_bytes())
    report_paths = defaultdict(list)
    for path in sorted((analysis_root / "fast-scan-reports").glob("*.json")):
        document, sha = read_json(path)
        if path.stat().st_mtime_ns <= result["cutoff_utc_ns"]:
            report_paths[document["recording_name"]].append((path, document, sha))
    retained, excluded = [], []
    for member in result["members"]:
        counts = {str(c): 0 for c in range(1, 9)}
        strong_counts = dict(counts)
        candidate_counts = dict(counts)
        selected = None
        # Choose one fixed published session; never union analysis runs.
        # Filenames retain the original fast input identity; published session
        # identities are transported inside source. The broad inventory already
        # groups these paths by that embedded identity.
        paths = member["tracking_inputs"]
        if paths:
            pinned = sorted(paths, key=lambda p: p["path"])[0]
            document, sha = read_json(Path(pinned["path"]))
            if sha != pinned["sha256"]:
                raise ValueError("pinned tracking input changed: " + pinned["path"])
            if document["source"]["session_id"] != member["session_id"]:
                raise ValueError("pinned tracking session identity mismatch")
            run_id = document.get("provenance", {}).get("run_id")
            for probe in document["source"].get("probes", []):
                passed = [
                    c
                    for c in probe.get("candidates", [])
                    if c.get("passed_fractional_margin_gate") is True
                ]
                key = str(probe["channel"])
                if key in counts:
                    counts[key] += bool(passed)
                    candidate_counts[key] += len(passed)
                    strong_counts[key] += any(c.get("fractional_margin", 0) >= 0.1 for c in passed)
            selected = {
                "kind": "pinned_tracking_input",
                "path": pinned["path"],
                "sha256": sha,
                "session_id": member["session_id"],
                "run_id": run_id,
                "gate": "passed_fractional_margin_gate",
                "margin_gate": 0.025,
            }
        else:
            choices = [
                r
                for r in report_paths.get(member["recording_id"], [])
                if r[1].get("session_id") == member["session_id"]
            ]
            if choices:
                desired = (member.get("automatic_job") or {}).get("document", {}).get("run_id")
                choices.sort(key=lambda r: (r[1].get("run_id") != desired, str(r[0])))
                path, document, sha = choices[0]
                snapshot = output / "glrt-qualification-sources" / path.name
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_bytes(path.read_bytes())
                margin_gate = document["policy"]["margin_gate"]
                for point in document.get("points", []):
                    key = str(point["channel"])
                    if key in counts and point.get("margin", 0) >= margin_gate:
                        counts[key] += 1
                        strong_counts[key] += point.get("margin", 0) >= 0.1
                candidate_counts = None
                selected = {
                    "kind": "original_glrt_report",
                    "path": str(path),
                    "sha256": sha,
                    "snapshot_path": str(snapshot.resolve()),
                    "session_id": document["session_id"],
                    "run_id": document["run_id"],
                    "gate": "report_point.margin >= policy.margin_gate",
                    "margin_gate": margin_gate,
                    "policy": document["policy"],
                }
        qualifies = all(v > 0 for v in counts.values())
        qualification = {
            "qualified": qualifies,
            "per_channel_passed_probe_receiver_counts": counts,
            "per_channel_strong_probe_receiver_counts": strong_counts,
            "strong_margin": 0.1,
            "per_channel_passed_candidate_counts": candidate_counts,
            "selected_analysis": selected,
            "missing_channels": [int(c) for c, n in counts.items() if n == 0],
        }
        member["glrt_qualification"] = qualification
        (retained if qualifies else excluded).append(member)
    result["members"] = retained
    result["glrt_excluded_members"] = excluded
    result["selection"] = (
        "raw recordings before frozen cutoff with >=1 GLRT margin-gate pass on each of "
        "channels1..8 across either receiver in one fixed analysis run; no tracklet gate"
    )
    result["qualification_run_selection"] = (
        "automatic published session if available, else fixed source-input session; "
        "pinned tracking input preferred, original matching-session GLRT report fallback; "
        "no union across runs"
    )
    result["broad_inventory_sha256"] = digest(broad.read_bytes())
    result["counts"] = {
        "members": len(retained),
        "broad_raw_members": len(retained) + len(excluded),
        "glrt_excluded": len(excluded),
        "complete": sum(m["recording_state"] == "complete" for m in retained),
        "incomplete": sum(m["recording_state"] != "complete" for m in retained),
        "with_tracking_input": sum(bool(m["tracking_inputs"]) for m in retained),
    }
    raw = (json.dumps(result, indent=2) + "\n").encode()
    manifest.write_bytes(raw)
    (output / "manifest.sha256").write_text(digest(raw) + "  manifest.json\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff-ns", type=int)
    parser.add_argument("--qualify-existing", action="store_true")
    parser.add_argument("--analysis-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--root", type=Path, action="append")
    args = parser.parse_args()
    if args.qualify_existing:
        result = qualify_existing(args.output, args.analysis_root)
        print(json.dumps(result["counts"]))
        return
    if args.cutoff_ns is None or not args.root:
        parser.error("inventory requires --cutoff-ns and --root")
    result = inventory(args.root, args.analysis_root, args.cutoff_ns)
    args.output.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(result, indent=2) + "\n").encode()
    (args.output / "manifest.json").write_bytes(raw)
    (args.output / "manifest.sha256").write_text(digest(raw) + "  manifest.json\n")
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
