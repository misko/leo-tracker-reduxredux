"""Freeze DS22 plus newer on-disk acquisitions; seal a random ten-scan sample."""

import hashlib
import importlib.util
import json
import random
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/2026_10_18_ds23_post_ds22"
PARENT = ROOT / "reports/2026_10_14_ds22_post_ds21/local"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def compact_member(member):
    keys = ("recording_id", "case_id", "session_id", "session_ids", "channels",
            "observed_channels", "captured_utc_ns", "recording_state", "window_count",
            "raw_authority_digest", "recording_format", "analysis_availability")
    result = {k: member[k] for k in keys if k in member}
    result.setdefault("recording_format", "short_window_iq_recording")
    for key in ("source_inputs", "tracking_inputs"):
        result[key] = [{k: v for k, v in row.items() if k not in ("segments", "document")}
                       for row in member.get(key, [])]
    raw = member["raw_recording"]
    result["raw_recording"] = {k: raw[k] for k in (
        "identity_sha256", "root", "duplicate_roots", "integrity_errors", "iq_hash_verification")
        if k in raw}
    result["raw_recording"]["segments"] = [
        {k: v for k, v in r.items() if k != "document"} for r in raw.get("segments", [])]
    result["raw_recording"]["chunks"] = raw.get("chunks", [])
    return result


def freeze_members(parent_members, new_members, cutoff, parent_cutoff, include_parent=True):
    """No format, completeness, GLRT, satellite or position selection gates."""
    admitted = []
    for member in new_members:
        if parent_cutoff < member["captured_utc_ns"] <= cutoff:
            admitted.append(("post_DS22", member))
    if include_parent:
        admitted.extend(("DS22", m) for m in parent_members)
    unique = {}
    for source, member in admitted:
        identity = member["raw_recording"]["identity_sha256"]
        if identity in unique:
            previous = unique[identity]
            if previous["captured_utc_ns"] != member["captured_utc_ns"]:
                raise ValueError("duplicate raw content disagrees on capture time")
            continue
        row = compact_member(member)
        row["membership_source"] = source
        row["parent_dataset_label"] = member.get("dataset_label")
        unique[identity] = row
    result = sorted(unique.values(), key=lambda r: (r["captured_utc_ns"], r["case_id"]))
    for i, member in enumerate(result, 1):
        member["dataset_label"] = f"DS23-{i:04d}"
    return result


def random_sample(members, size, seed):
    population = sorted(members, key=lambda r: r["dataset_label"])
    if len(population) < size:
        raise ValueError("fewer recordings than the predeclared sample size")
    return random.Random(seed).sample(population, size)


def run():
    if (OUTPUT / "manifest.json").exists():
        raise ValueError("DS23 already frozen; refusing to rewrite membership")
    request = json.loads((OUTPUT / "freeze_request.json").read_text())
    cutoff = request["cutoff_utc_ns"]
    expected = (PARENT / "manifest.sha256").read_text().split()[0]
    if digest(PARENT / "manifest.json") != expected:
        raise ValueError("DS22 parent authority digest mismatch")
    parent = json.loads((PARENT / "manifest.json").read_bytes())
    if parent["dataset_id"] != "DS22" or parent["cutoff_utc_ns"] != request["parent_cutoff_utc_ns"]:
        raise ValueError("wrong parent dataset boundary")
    # Reuse the existing read-only metadata collector, without embedding its
    # repeated analysis/index documents in the new membership authority.
    import sys

    source = ROOT / "reports/2026_10_14_ds22_post_ds21"
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location("ds22_mint_adapter", source / "mint.py")
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    roots = [Path(p) for p in parent["discovery_roots"]]
    for base in (Path("/srv/bulk/leo"), Path("/srv/postgres-nvme")):
        roots.extend(p for p in base.iterdir()
                     if p.is_dir() and p.name.startswith(("fast8-", "fast-scan-recordings")))
    roots = sorted(set(roots))
    # pathlib.rglob can suppress permission failures. Check each existing root
    # explicitly so an unreadable live corpus cannot become an empty dataset.
    for root in roots + [Path("/srv/bulk/leo/scanner-adaptive-recordings")]:
        if root.exists():
            next(root.iterdir(), None)
    print("Discovering fast acquisition metadata", len(roots), flush=True)
    # Group every available segment first, then apply the whole-acquisition
    # START cutoff. A later segment must not truncate a recording at cutoff.
    result = old.inventory(roots, Path("/srv/bulk/leo"), 2**63 - 1,
                           start_ns=parent["cutoff_utc_ns"] + 1, dataset_id="DS23",
                           required_channels=None)
    print("Fast metadata complete", len(result["members"]), flush=True)
    if result["discovery_errors"]:
        write(OUTPUT / "discovery_errors.json", result["discovery_errors"])
        raise ValueError("fast discovery errors require reconciliation")
    census = old.legacy_census(parent["cutoff_utc_ns"] + 1, cutoff)
    if census["errors"]:
        write(OUTPUT / "discovery_errors.json", census["errors"])
        raise ValueError("legacy discovery errors require reconciliation")
    print("Legacy metadata complete", len(census["members"]), flush=True)
    newer = result["members"] + [old.legacy_member(r) for r in census["members"]]
    members = freeze_members(parent["members"], newer, cutoff, parent["cutoff_utc_ns"],
                             request["inclusive_DS22"])
    counts = old.counts(members)
    manifest = dict(schema="ds23-recording-membership/v1", dataset_id="DS23",
                    created_utc=datetime.now(UTC).isoformat(),
                    cutoff_utc_ns=cutoff, cutoff_utc=request["cutoff_utc"],
                    parent_dataset="DS22", parent_cutoff_utc_ns=parent["cutoff_utc_ns"],
                    parent_manifest_sha256=expected, inclusive_DS22=request["inclusive_DS22"],
                    selection=("DS22 plus newer manifested acquisition starts through cutoff"
                               if request["inclusive_DS22"] else
                               "All manifested acquisition starts strictly after DS22 cutoff"),
                    start_utc_ns=parent["cutoff_utc_ns"],
                    analysis_readiness_required=False, complete_recording_required=False,
                    scientific_outcomes_used_for_membership=False,
                    discovery_roots=list(map(str, roots)),
                    legacy_discovery_roots=census["roots"], counts=counts, members=members,
                    metadata_snapshot_is_atomic=False, payloads_copied_or_rehashed=False,
                    source_sha256=digest(Path(__file__)))
    write(OUTPUT / "manifest.json", manifest)
    sha = digest(OUTPUT / "manifest.json")
    (OUTPUT / "manifest.sha256").write_text(sha + "  manifest.json\n")
    selected = random_sample(members, request["sample_size"], request["random_seed"])
    sample = dict(dataset_id="DS23", manifest_sha256=sha, seed=request["random_seed"],
                  sampling="uniform without replacement over all frozen members; no substitutions",
                  sampled_before_position_or_association_results=True,
                  no_format_quality_or_location_selection=True, selected=selected)
    write(OUTPUT / "random_sample_10.json", sample)
    write(OUTPUT / "seal.json", dict(dataset_id="DS23", files={
        name: digest(OUTPUT / name) for name in (
            "manifest.json", "manifest.sha256", "freeze_request.json", "random_sample_10.json")}))
    write(OUTPUT / "discovery_summary.json", dict(
        fast_manifest_paths=result.get("checked_manifest_count"),
        legacy_checked=census["checked"],
        parent_members=len(parent["members"]), post_DS22=sum(
            m["membership_source"] == "post_DS22" for m in members),
        unadmitted_future_fast_starts=sum(m["captured_utc_ns"] > cutoff
                                       for m in result["members"]), counts=counts))
    print(json.dumps(dict(counts=counts, selected=[m["dataset_label"] for m in selected])),
          flush=True)


if __name__ == "__main__":
    run()
