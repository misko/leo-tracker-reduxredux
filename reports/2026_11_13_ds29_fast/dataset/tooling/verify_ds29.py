#!/usr/bin/env python3
"""Independently recompute sealed DS29 boundaries and metadata identities."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def verify(root):
    raw = (root / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    parent_raw = (root / "parent-manifest.json").read_bytes()
    parent = json.loads(parent_raw)
    assert (manifest["dataset_id"], manifest["revision"]) == ("DS29", 1)
    assert digest(parent_raw) == manifest["parent_manifest_sha256"]
    assert parent_raw == Path(manifest["parent_manifest_path"]).read_bytes()
    assert manifest["start_utc_ns"] == parent["cutoff_utc_ns"] == 1793543987024292987
    assert manifest["cutoff_utc_ns"] == int(datetime(2026, 11, 13, 4, 55, tzinfo=UTC).timestamp()) * 10**9
    seen = set()
    source_paths = set()
    starts = []
    for number, member in enumerate(manifest["members"], 1):
        assert member["dataset_label"] == f"DS29-{number:04d}"
        recording = member["raw_recording"]
        segments = []
        for receipt in recording["segments"]:
            segment_raw = Path(receipt["path"]).read_bytes()
            assert digest(segment_raw) == receipt["sha256"]
            value = json.loads(segment_raw)
            value = value.get("manifest", value.get("document", value))
            assert value["kind"] == "short_window_iq_recording"
            segments.append(value)
            source_paths.add(receipt["path"])
        acquired = min((s.get("timing") or {}).get("first_sample_estimate_utc_ns") or s["created_utc_ns"] for s in segments)
        assert acquired == member["captured_utc_ns"]
        assert manifest["start_utc_ns"] <= acquired < manifest["cutoff_utc_ns"]
        starts.append(acquired)
        content = sorted((chunk["compressed_sha256"], chunk["index_sha256"])
                         for segment in segments for chunk in segment.get("chunks", []))
        expected = digest(json.dumps(content, separators=(",", ":")).encode()) if content else digest(
            json.dumps(sorted(s["sha256"] for s in recording["segments"])).encode())
        assert expected == recording["identity_sha256"]
        assert expected not in seen
        seen.add(expected)
        for receipt in member["source_inputs"] + member["tracking_inputs"] + member.get("recording_metadata", []):
            assert digest(Path(receipt["path"]).read_bytes()) == receipt["sha256"]
            source_paths.add(receipt["path"])
    assert not seen & {m["raw_recording"]["identity_sha256"] for m in parent["members"]}
    for name, sha in json.loads((root / "seal.json").read_bytes())["files"].items():
        assert digest((root / name).read_bytes()) == sha
    for path, sha in manifest["inventory_source_sha256"].items():
        assert digest(Path(path).read_bytes()) == sha
    discovery = json.loads((root / "discovery.json").read_bytes())
    assert not discovery["errors"]
    units = json.loads((root / "evaluation-units.json").read_bytes())
    sample = json.loads((root / "sample.json").read_bytes())
    assert units["case_ids"] == [m["case_id"] for m in manifest["members"]]
    assert [m["case_id"] for m in sample["selected"]] == units["case_ids"]
    return dict(verified=True, verifier_sha256=digest(Path(__file__).read_bytes()), manifest_sha256=digest(raw),
                parent_bytes_preserved=True, sources_checked=len(source_paths),
                boundaries_recomputed=True, content_identities_recomputed=True, parent_content_overlap=0,
                membership_count=len(seen), minimum_capture_utc_ns=min(starts), maximum_capture_utc_ns=max(starts),
                checked_manifests=sum(row["checked_manifests"] for row in discovery["roots"]),
                discovery_roots=len(discovery["roots"]), existing_discovery_roots=sum(row["exists"] for row in discovery["roots"]),
                discovery_errors=discovery["errors"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.root)
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded)
