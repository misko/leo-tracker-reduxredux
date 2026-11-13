#!/usr/bin/env python3
"""Seal all fast acquisitions after DS28 revision 2 through a fixed UTC cutoff."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUPPORT = HERE / "support"
sys.path.insert(0, str(SUPPORT))
import freeze_ds28 as pinned
import raw_inventory
import mint
import freeze_ds23_dataset as compact

CUTOFF = int(datetime(2026, 11, 13, 4, 55, tzinfo=UTC).timestamp()) * 10**9
PARENT = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds28_revision2/dataset/manifest.json")
EXTRA_ROOTS = [Path("/mnt/qnap01/mouse9911") / name for name in
               ("leo/captures", "leo/staging", "leo-store", "leo-scans", "leo-cropped")]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def census(roots, start, cutoff):
    audit = dict(roots=[], errors=[], nonrecording_in_window=[], selected_fast_roots=[],
                 selected_adaptive_manifests=[], timestamp_fallback_reads=0)
    selected = set()
    for root in roots:
        try:
            part, fast, _ = pinned.census([root], start, cutoff)
        except (OSError, ValueError, KeyError) as error:
            audit["errors"].append(dict(root=str(root), error=repr(error)))
            continue
        selected.update(fast)
        for key in ("roots", "nonrecording_in_window", "selected_adaptive_manifests"):
            audit[key].extend(part[key])
        audit["timestamp_fallback_reads"] += part["timestamp_fallback_reads"]
    audit["selected_fast_roots"] = [str(p) for p in sorted(selected)]
    audit["adaptive_excluded_by_recording_format"] = len(audit["selected_adaptive_manifests"])
    return audit, sorted(selected)


def collect_members(fast_roots, analysis_root):
    original_identity = raw_inventory.group_identity

    def identity(segments):
        if any(s["document"].get("chunks") for s in segments):
            return original_identity(segments)
        return pinned.digest(json.dumps(sorted(s["sha256"] for s in segments)).encode())

    raw_inventory.group_identity = identity
    try:
        inventory = raw_inventory.inventory(fast_roots, analysis_root, 2**63 - 1,
                                            start_ns=0, dataset_id="DS29", required_channels=None)
    finally:
        raw_inventory.group_identity = original_identity
    if inventory["discovery_errors"]:
        raise ValueError("raw inventory discovery errors: " + repr(inventory["discovery_errors"]))
    members = []
    for member in inventory["members"]:
        row = compact.compact_member(member)
        segments = member["raw_recording"]["segments"]
        row["captured_utc_ns"] = min(pinned.capture_time(s["document"]) for s in segments)
        row["sample_rates_hz"] = sorted({rate for s in segments for rate in pinned.sample_rates(s["document"])})
        row["sample_rate_hz"] = row["sample_rates_hz"][0] if len(row["sample_rates_hz"]) == 1 else None
        row["recording_metadata"] = []
        run = Path(row["raw_recording"]["root"]) / "run.json"
        if run.exists():
            raw = run.read_bytes()
            state = json.loads(raw)
            row["recording_metadata"].append(dict(path=str(run), sha256=pinned.digest(raw),
                                                   state=state.get("state"), fault=state.get("fault")))
            if state.get("state") not in ("stopped", "complete") or state.get("fault"):
                row["recording_state"] = "incomplete"
        row["raw_manifest_digest"] = pinned.digest(json.dumps(
            [(Path(s["path"]).parent.name, s["sha256"]) for s in row["raw_recording"]["segments"]],
            separators=(",", ":")).encode())
        row["raw_authority_digest"] = row.get("raw_authority_digest") or row["raw_manifest_digest"]
        row["analysis_availability"] = "existing_tracking_contract" if row["tracking_inputs"] else "existing_tracking_contract_unavailable"
        row["glrt_availability"] = dict(available=bool(row["tracking_inputs"]),
                                        kind="published_fast_tracking_contract",
                                        verification_scope="metadata hash checked; evaluation validates source")
        members.append(row)
    return members


def verify_sources(members):
    checked = {}
    for member in members:
        for row in (member["raw_recording"]["segments"] + member["source_inputs"]
                    + member["tracking_inputs"] + member.get("recording_metadata", [])):
            path = row["path"]
            actual = checked.setdefault(path, pinned.digest(Path(path).read_bytes()))
            if actual != row["sha256"]:
                raise ValueError("source changed during inventory: " + path)
    return len(checked)


def verify(output, check_sources=True):
    manifest = json.loads((output / "manifest.json").read_bytes())
    parent = json.loads((output / "parent-manifest.json").read_bytes())
    members = manifest["members"]
    identities = {m["raw_recording"]["identity_sha256"] for m in members}
    overlap = identities & {m["raw_recording"]["identity_sha256"] for m in parent["members"]}
    if len(identities) != len(members) or overlap:
        raise ValueError("duplicate or parent-overlapping identities")
    if manifest["start_utc_ns"] != parent["cutoff_utc_ns"]:
        raise ValueError("parent boundary mismatch")
    if any(not manifest["start_utc_ns"] <= m["captured_utc_ns"] < manifest["cutoff_utc_ns"] for m in members):
        raise ValueError("member outside interval")
    if any(m["recording_format"] != "short_window_iq_recording" for m in members):
        raise ValueError("non-fast member")
    if pinned.digest((output / "parent-manifest.json").read_bytes()) != manifest["parent_manifest_sha256"]:
        raise ValueError("parent changed")
    units = json.loads((output / "evaluation-units.json").read_bytes())
    if units["case_ids"] != [m["case_id"] for m in members]:
        raise ValueError("evaluation membership mismatch")
    seal = output / "seal.json"
    if seal.exists():
        for name, sha in json.loads(seal.read_bytes())["files"].items():
            if pinned.digest((output / name).read_bytes()) != sha:
                raise ValueError("seal mismatch: " + name)
    return dict(verified=True, sources_rechecked=check_sources,
                metadata_source_count=verify_sources(members) if check_sources else None,
                unique_content_identities=len(identities), parent_content_overlap=len(overlap),
                manifest_sha256=pinned.digest((output / "manifest.json").read_bytes()))


def freeze(args):
    output = args.output.resolve()
    if Path("/mnt/qnap01") == output or Path("/mnt/qnap01") in output.parents:
        raise ValueError("output must be local")
    if (output / "manifest.json").exists() or (output / "seal.json").exists():
        raise ValueError("refusing to overwrite frozen membership")
    output.mkdir(parents=True, exist_ok=True)
    parent_raw = args.parent.read_bytes()
    parent = json.loads(parent_raw)
    if (parent["dataset_id"], parent["revision"]) != ("DS28", 2) or args.cutoff_ns <= parent["cutoff_utc_ns"]:
        raise ValueError("expected DS28 revision 2 and advancing cutoff")
    roots = sorted(set(pinned.discovery_roots(parent, args.base) + args.root))
    audit, fast_roots = census(roots, parent["cutoff_utc_ns"], args.cutoff_ns)
    audit["prior_attempts"] = [dict(status="interrupted_before_membership_write",
        reason="Broad QNAP leo root traversed historical analysis reports; restarted with documented raw captures and staging roots"),
        dict(status="permission_denied_reconciled", path="/srv/bulk/leo/fast-scan-recordings",
             reason="Unprivileged directory listing denied; final census uses root read-only access")]
    write(output / "discovery.json", audit)
    if audit["errors"]:
        raise ValueError("census incomplete; see discovery.json")
    members = pinned.freeze_members(collect_members(fast_roots, args.analysis_root), parent, args.cutoff_ns, "DS29")
    verify_sources(members)
    counts = mint.counts(members)
    counts.update(with_available_glrt_manifest=sum(m["glrt_availability"]["available"] for m in members),
                  sample_rate_counts=dict(Counter(str(m["sample_rate_hz"]) for m in members)))
    source_files = [Path(__file__).resolve(), HERE / "test_freeze_ds29.py", *sorted(SUPPORT.glob("*.py"))]
    for source in source_files:
        destination = output / "tooling" / source.relative_to(HERE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    manifest = dict(schema="post-ds26-recording-membership/v1", dataset_id="DS29", revision=1,
                    created_utc=datetime.now(UTC).isoformat(), start_utc_ns=parent["cutoff_utc_ns"],
                    cutoff_utc_ns=args.cutoff_ns, interval="[start_utc_ns, cutoff_utc_ns)",
                    parent_dataset="DS28 revision 2", parent_manifest_path=str(args.parent),
                    parent_manifest_sha256=pinned.digest(parent_raw),
                    selection="All discovered whole fast acquisitions starting at or after DS28 revision 2 cutoff and before fixed cutoff; all rates; no readiness, completeness, channel, signal or localization gate",
                    analysis_readiness_required=False, complete_recording_required=False,
                    scientific_outcomes_used_for_membership=False, metadata_snapshot_is_atomic=False,
                    payloads_copied_or_rehashed=False, census_privilege=f"uid={os.geteuid()} metadata reads only",
                    adapter_deviations=dict(acquisition_timestamp="minimum first_sample_estimate_utc_ns, falling back to created_utc_ns, across every acquisition segment",
                        empty_chunk_identity="SHA256 of sorted segment manifest SHA256 values; prevents unrelated empty failures merging",
                        nonempty_chunk_identity="unchanged pinned raw_inventory content identity"),
                    discovery_roots=[str(p) for p in roots], counts=counts, members=members,
                    inventory_source_sha256={str(p): pinned.digest(p.read_bytes()) for p in source_files})
    (output / "parent-manifest.json").write_bytes(parent_raw)
    write(output / "manifest.json", manifest)
    raw = (output / "manifest.json").read_bytes()
    sha = pinned.digest(raw)
    (output / "manifest.sha256").write_text(sha + "  manifest.json\n")
    (output / "manifest.json.gz").write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
    selected = []
    for member in members:
        row = {k: v for k, v in member.items() if k != "raw_recording"}
        row.update(raw_identity_sha256=member["raw_recording"]["identity_sha256"],
                   raw_manifest_receipts=member["raw_recording"]["segments"], mode="fast")
        selected.append(row)
    write(output / "sample.json", dict(study="DS29", dataset_manifest_sha256=sha,
                                        sampling="all members; unavailable inputs retained", selected=selected))
    write(output / "membership-summary.json", dict(dataset_id="DS29", manifest_sha256=sha, counts=counts,
            members=[{k: m.get(k) for k in ("dataset_label", "case_id", "recording_id", "session_id", "mode", "captured_utc_ns", "sample_rate_hz", "recording_state", "raw_identity_sha256", "glrt_availability")} for m in selected]))
    write(output / "evaluation-units.json", dict(dataset_id="DS29", manifest_sha256=sha,
            case_ids=[m["case_id"] for m in members], dataset_labels=[m["dataset_label"] for m in members]))
    write(output / "verification.json", dict(verify(output), adapter_deviations=manifest["adapter_deviations"], **counts))
    write(output / "seal.json", dict(files={str(p.relative_to(output)): pinned.digest(p.read_bytes())
            for p in sorted(output.rglob("*")) if p.is_file() and p.name != "seal.json" and "__pycache__" not in p.parts}))
    print(json.dumps(dict(manifest_sha256=sha, cutoff_utc_ns=args.cutoff_ns, **counts)), flush=True)


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--parent", type=Path, default=PARENT)
    value.add_argument("--cutoff-ns", type=int, default=CUTOFF)
    value.add_argument("--analysis-root", type=Path, default=Path("/srv/bulk/leo"))
    value.add_argument("--base", type=Path, action="append", default=[Path("/srv/bulk/leo"), Path("/srv/postgres-nvme")])
    value.add_argument("--root", type=Path, action="append", default=EXTRA_ROOTS)
    value.add_argument("--verify", action="store_true")
    return value


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(verify(args.output)), flush=True) if args.verify else freeze(args)
