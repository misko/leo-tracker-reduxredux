#!/usr/bin/env python3
"""Freeze all new on-disk acquisitions after DS24, using metadata reads only.

The three metadata collectors supplied with --support are pinned snapshots from
the separately sealed DS24 extension. They are research adapters, not numerical
oracles. Every write stays within --output; existing memberships are immutable.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def document(value: dict) -> dict:
    return value.get("manifest", value.get("document", value))


def capture_time(value: dict) -> int:
    value = document(value)
    return (value.get("timing") or {}).get("first_sample_estimate_utc_ns") or value[
        "created_utc_ns"
    ]


def sample_rates(value: dict) -> list[int]:
    """Read capture settings; radio restoration settings are not observations."""
    value = document(value)
    plan = value.get("receipt", {}).get("plan", value.get("plan", {}))
    values = [
        value.get("sample_rate_hz"),
        value.get("configuration", {}).get("sample_rate_hz"),
        (value.get("timing") or {}).get("sample_rate_hz"),
        plan.get("sample_rate_hz"),
        plan.get("geometry", {}).get("sample_rate_hz"),
    ]
    return sorted({v for v in values if v is not None})


def freeze_members(members: list[dict], parent: dict, cutoff: int, dataset_id: str) -> list[dict]:
    """Select whole acquisitions by start, deduplicate copies, retain failures."""
    start = parent["cutoff_utc_ns"]
    old = {m["raw_recording"]["identity_sha256"] for m in parent["members"]}
    result = {}
    for member in members:
        if not start <= member["captured_utc_ns"] < cutoff:
            continue
        identity = member["raw_recording"]["identity_sha256"]
        if identity in old:
            raise ValueError("new interval overlaps parent content identity")
        if identity in result:
            previous = result[identity]
            if previous["captured_utc_ns"] != member["captured_utc_ns"]:
                raise ValueError("duplicate raw content disagrees on acquisition start")
            roots = previous["raw_recording"]["duplicate_roots"]
            roots.extend([member["raw_recording"]["root"], *member["raw_recording"].get("duplicate_roots", [])])
            previous["raw_recording"]["duplicate_roots"] = sorted(set(roots))
            continue
        result[identity] = copy.deepcopy(member)
    ordered = sorted(result.values(), key=lambda m: (m["captured_utc_ns"], m["case_id"]))
    for number, member in enumerate(ordered, 1):
        member["dataset_label"] = f"{dataset_id}-{number:04d}"
    return ordered


def discovery_roots(parent: dict, bases: list[Path]) -> list[Path]:
    roots = {Path(p) for p in parent.get("discovery_roots", []) + parent.get("additional_discovery_roots", [])}
    for base in bases:
        for path in base.iterdir():
            if path.is_dir() and (
                path.name.startswith(("fast8-", "fast-scan-recordings"))
                or "recording" in path.name
                or path.name in ("spool", "leo-scanner-spool", "leo-scanner-staging")
            ):
                roots.add(path)
    return sorted(roots)


def paths_under(root: Path):
    """Unlike rglob, report directory traversal permission failures."""
    def fail(error):
        raise error

    for directory, dirs, files in os.walk(root, onerror=fail):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if "manifest.json" in files:
            yield Path(directory) / "manifest.json"


def census(roots: list[Path], start: int, cutoff: int) -> tuple[dict, list[Path], list[dict]]:
    fast = defaultdict(list)
    others = []
    audit = {"roots": [], "nonrecording_in_window": [], "errors": [], "timestamp_fallback_reads": 0}
    for root in roots:
        row = {"path": str(root), "resolved_path": str(root.resolve()), "exists": root.exists(), "checked_manifests": 0}
        audit["roots"].append(row)
        if not root.exists():
            continue
        next(root.iterdir(), None)
        for path in paths_under(root):
            row["checked_manifests"] += 1
            with path.open("rb") as handle:
                prefix = handle.read(16384)
                handle.seek(max(0, path.stat().st_size - 16384))
                suffix = handle.read()
            times = re.findall(rb'"first_sample_estimate_utc_ns"\s*:\s*(\d+)', suffix)
            if not times:
                times = re.findall(rb'"created_utc_ns"\s*:\s*(\d+)', prefix + suffix)
            value = None
            if not times:
                audit["timestamp_fallback_reads"] += 1
                value = json.loads(path.read_bytes())
                try:
                    stamp = capture_time(value)
                except KeyError:
                    # Non-recording metadata, e.g. a historical analysis report.
                    if document(value).get("kind", "").endswith(("_iq", "_recording")):
                        raise ValueError("raw recording lacks acquisition time: " + str(path)) from None
                    continue
            else:
                stamp = int(times[0])
            # Fast groups need all segments, including any beyond the cutoff.
            kind_in_prefix = b'"short_window_iq_recording"' in prefix
            if not kind_in_prefix and not start <= stamp < cutoff:
                continue
            raw = path.read_bytes()
            value = document(json.loads(raw))
            kind = value.get("kind")
            item = dict(path=str(path), sha256=digest(raw), document=json.loads(raw))
            if kind == "short_window_iq_recording":
                fast[path.parent.parent].append(item)
            elif start <= capture_time(value) < cutoff:
                if kind == "starlink_adaptive_hop_iq":
                    others.append(item)
                elif value.get("chunks"):
                    raise ValueError("new recording requires explicit format adapter: " + str(path))
                else:
                    audit["nonrecording_in_window"].append(dict(path=str(path), kind=kind))
        print("Census", root, row["checked_manifests"], flush=True)
    selected_fast = [root for root, segments in fast.items() if start <= min(capture_time(s["document"]) for s in segments) < cutoff]
    audit["selected_fast_roots"] = [str(p) for p in sorted(selected_fast)]
    audit["selected_adaptive_manifests"] = [{k: v for k, v in row.items() if k != "document"} for row in others]
    return audit, sorted(selected_fast), others


def load_support(support: Path):
    sys.path.insert(0, str(support))
    modules = []
    for name in ("raw_inventory", "mint", "freeze_ds23_dataset"):
        spec = importlib.util.spec_from_file_location(name, support / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def adaptive_availability(member: dict, captures, analyses) -> dict:
    from leo.contracts.digests import canonical_digest
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.errors import BundleNotFoundError

    publication = captures.inspect(member["session_id"])
    binding = bind_actual_visit_analysis(publication.manifest.receipt,
        input_manifest_sha256=publication.manifest_sha256, probe_stride_ms=120)
    result = dict(kind="adaptive_public_analysis", session_id=member["session_id"],
        input_manifest_sha256=publication.manifest_sha256, binding_sha256=binding.sha256,
        adaptive_probe_stride_ms=120)
    try:
        with analyses.job(binding) as job:
            metrics = job.manifest()
    except BundleNotFoundError as error:
        return dict(result, available=False, reason=str(error))
    if metrics is None:
        return dict(result, available=False, reason="adaptive metrics are unpublished")
    return dict(result, available=True, analysis_manifest_sha256=canonical_digest(metrics.model_dump(mode="json")),
        published_visit_count=len(metrics.visits), complete_visit_count=metrics.complete_visit_count,
        verification_scope="public capture and metrics manifests; visit payloads loaded by evaluation")


def main(args):
    output = args.output.resolve()
    if output == Path("/mnt/qnap01") or Path("/mnt/qnap01") in output.parents:
        raise ValueError("dataset output must be local")
    if (output / "manifest.json").exists():
        raise ValueError("refusing to overwrite frozen membership")
    output.mkdir(parents=True, exist_ok=True)
    parent_raw = args.parent.read_bytes()
    parent = json.loads(parent_raw)
    if parent["dataset_id"] != "DS24" or args.cutoff_ns <= parent["cutoff_utc_ns"]:
        raise ValueError("invalid parent or cutoff")
    support = args.support.resolve()
    raw_collector, legacy, compact = load_support(support)
    roots = discovery_roots(parent, args.base)
    audit, fast_roots, adaptive = census(roots, parent["cutoff_utc_ns"], args.cutoff_ns)
    write(output / "discovery.json", audit)
    print("Eligible roots", len(fast_roots), "adaptive manifests", len(adaptive), flush=True)
    inventory = raw_collector.inventory(fast_roots, args.analysis_root, 2**63 - 1,
        start_ns=parent["cutoff_utc_ns"], dataset_id=args.dataset_id, required_channels=None)
    if inventory["discovery_errors"]:
        raise ValueError("discovery errors: " + str(inventory["discovery_errors"]))
    members = []
    for member in inventory["members"]:
        row = compact.compact_member(member)
        rates = sorted({rate for segment in member["raw_recording"]["segments"] for rate in sample_rates(segment["document"])})
        row["sample_rates_hz"] = rates
        row["sample_rate_hz"] = rates[0] if len(rates) == 1 else None
        row["recording_metadata"] = []
        run = Path(row["raw_recording"]["root"]) / "run.json"
        if run.exists():
            raw = run.read_bytes()
            state = json.loads(raw)
            row["recording_metadata"].append(dict(path=str(run), sha256=digest(raw), state=state.get("state"), fault=state.get("fault")))
            if state.get("state") not in ("stopped", "complete") or state.get("fault"):
                row["recording_state"] = "incomplete"
        row["raw_manifest_digest"] = digest(json.dumps([(Path(s["path"]).parent.name, s["sha256"]) for s in row["raw_recording"]["segments"]], separators=(",", ":")).encode())
        row["raw_authority_digest"] = row.get("raw_authority_digest") or row["raw_manifest_digest"]
        row["analysis_availability"] = "existing_tracking_contract" if row["tracking_inputs"] else "existing_tracking_contract_unavailable"
        row["glrt_availability"] = dict(available=bool(row["tracking_inputs"]), kind="published_fast_tracking_contract", verification_scope="pinned public contract file; evaluation validates source")
        members.append(row)
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
    captures = AdaptiveHopIqStore(args.analysis_root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(args.analysis_root, read_only=True)
    try:
        for number, source in enumerate(adaptive, 1):
            row = compact.compact_member(legacy.legacy_member(source))
            rates = sample_rates(source["document"])
            row["sample_rates_hz"] = rates
            row["sample_rate_hz"] = rates[0] if len(rates) == 1 else None
            row["glrt_availability"] = adaptive_availability(row, captures, analyses)
            row["analysis_availability"] = "existing_public_adaptive_analysis" if row["glrt_availability"]["available"] else "existing_public_adaptive_analysis_unavailable"
            members.append(row)
            if number % 25 == 0:
                print("Adaptive availability", number, flush=True)
    finally:
        captures.close()
        analyses.close()
    members = freeze_members(members, parent, args.cutoff_ns, args.dataset_id)
    for member in members:
        for item in member["raw_recording"]["segments"] + member["source_inputs"] + member["tracking_inputs"] + member.get("recording_metadata", []):
            if digest(Path(item["path"]).read_bytes()) != item["sha256"]:
                raise ValueError("source changed during inventory: " + item["path"])
    counts = legacy.counts(members)
    counts["with_available_glrt_manifest"] = sum(m["glrt_availability"]["available"] for m in members)
    counts["sample_rate_counts"] = dict(Counter(str(m["sample_rate_hz"]) for m in members))
    result = dict(schema="post-ds24-recording-membership/v1", dataset_id=args.dataset_id, revision=1,
        created_utc=datetime.now(UTC).isoformat(), start_utc_ns=parent["cutoff_utc_ns"], cutoff_utc_ns=args.cutoff_ns,
        interval="[start_utc_ns, cutoff_utc_ns)", parent_dataset="DS24 revision 2",
        parent_manifest_path=str(args.parent), parent_manifest_sha256=digest(parent_raw),
        selection="All discovered whole fast and adaptive acquisitions starting after the DS24 boundary through the frozen cutoff; all sample rates; no readiness, completeness, channel, signal, or localization gate",
        analysis_readiness_required=False, complete_recording_required=False, scientific_outcomes_used_for_membership=False,
        metadata_snapshot_is_atomic=False, payloads_copied_or_rehashed=False,
        census_privilege="root for historical permissions; earlier leo access failures reconciled by root read-only census",
        discovery_roots=[str(p) for p in roots], counts=counts, members=members,
        inventory_source_sha256={str(p): digest(p.read_bytes()) for p in [Path(__file__).resolve(), *sorted(support.glob("*.py"))]})
    (output / "parent-manifest.json").write_bytes(parent_raw)
    write(output / "manifest.json", result)
    manifest_raw = (output / "manifest.json").read_bytes()
    sha = digest(manifest_raw)
    (output / "manifest.json.gz").write_bytes(gzip.compress(manifest_raw, compresslevel=6, mtime=0))
    (output / "manifest.sha256").write_text(sha + "  manifest.json\n")
    selected = []
    for member in members:
        row = {k: v for k, v in member.items() if k != "raw_recording"}
        row["raw_identity_sha256"] = member["raw_recording"]["identity_sha256"]
        row["raw_authority_digest"] = member.get("raw_authority_digest") or row["raw_identity_sha256"]
        row["raw_manifest_receipts"] = member["raw_recording"]["segments"]
        row["mode"] = "adaptive" if member["recording_format"] == "starlink_adaptive_hop_iq" else "fast"
        selected.append(row)
    write(output / "sample.json", dict(study=args.dataset_id, dataset_manifest_sha256=sha, sampling="all members; unavailable inputs retained", selected=selected))
    write(output / "membership-summary.json", dict(dataset_id=args.dataset_id, manifest_sha256=sha, counts=counts,
        members=[{k: row.get(k) for k in ("dataset_label", "case_id", "recording_id", "session_id", "mode", "captured_utc_ns", "sample_rate_hz", "recording_state", "raw_identity_sha256", "glrt_availability")} for row in selected]))
    write(output / "evaluation-units.json", dict(dataset_id=args.dataset_id, manifest_sha256=sha,
        case_ids=[m["case_id"] for m in members], dataset_labels=[m["dataset_label"] for m in members]))
    write(output / "verification.json", dict(verified=True, sources_rechecked=True, unique_content_identities=len(members),
        parent_content_overlap=0, **counts))
    write(output / "seal.json", dict(files={str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name != "seal.json" and "__pycache__" not in p.parts}))
    print(json.dumps(counts), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--cutoff-ns", type=int, required=True)
    parser.add_argument("--analysis-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--base", type=Path, action="append", default=[Path("/srv/bulk/leo"), Path("/srv/postgres-nvme")])
    main(parser.parse_args())
