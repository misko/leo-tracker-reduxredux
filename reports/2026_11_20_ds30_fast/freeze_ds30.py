"""Freeze or independently verify the next whole-fast-acquisition membership on Gauss."""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

START = 1794545700000000000
CUTOFF = 1795217825000000000
PARENT_SHA = "sha256:b9b7dfc497f1df45e913e175be9b9471b1e0b49eab601f0aeff640c5c05c61a8"
PRIOR = Path("/srv/bulk/leo-dev/ds29-20261113")
ARCHIVE = Path("/srv/bulk/leo")
BASE = Path("/srv/bulk/leo-dev/ds30-20261120")
HERE = Path(__file__).resolve().parent


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def bound(entry):
    raw = Path(entry["path"]).read_bytes()
    if digest(raw) != entry["sha256"]:
        raise ValueError("changed source: " + entry["path"])
    return raw


def collectors():
    seal = read(PRIOR / "dataset/seal.json")["files"]
    for name in (
        "freeze_ds29.py",
        "support/raw_inventory.py",
        "support/freeze_ds28.py",
        "support/mint.py",
        "support/freeze_ds23_dataset.py",
    ):
        if digest((PRIOR / "tooling" / name).read_bytes()) != seal["tooling/" + name]:
            raise ValueError("DS29 inventory algorithm changed: " + name)
    sys.path.insert(0, str(PRIOR / "tooling"))
    import freeze_ds29

    return freeze_ds29


def parent_document():
    raw = (PRIOR / "dataset/manifest.json").read_bytes()
    if digest(raw) != PARENT_SHA:
        raise ValueError("wrong DS29 parent")
    parent = json.loads(raw)
    if (parent["dataset_id"], parent["revision"], parent["cutoff_utc_ns"]) != ("DS29", 1, START):
        raise ValueError("unexpected DS29 revision or boundary")
    return parent


def roots_for(prior, parent):
    return sorted(
        set(
            prior.pinned.discovery_roots(parent, [ARCHIVE, Path("/srv/postgres-nvme")])
            + prior.EXTRA_ROOTS
        )
    )


def audit_ledger(members):
    # An automatic job is a second inventory of acquisition names. Its processing
    # clock can lag capture. Use the recorded UTC naming convention for reconciliation.
    names = {
        Path(p).name
        for row in members
        for p in [row["raw_recording"]["root"], *row["raw_recording"]["duplicate_roots"]]
    }
    present, missing = [], []
    pattern = re.compile(r"fast8-auto-(\d{8}-\d{6})-")
    for p in sorted((ARCHIVE / "fast-scan-automatic").glob("*.json")):
        match = pattern.match(p.stem)
        if not match:
            continue
        utc = datetime.strptime(match[1], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
        if not START <= int(utc.timestamp()) * 10**9 < CUTOFF:
            continue
        if p.stem in names:
            present.append(p.stem)
        else:
            raw = p.read_bytes()
            job = json.loads(raw)
            missing.append(
                dict(
                    recording_id=p.stem,
                    ledger_sha256=digest(raw),
                    state=job.get("state"),
                    captured_windows=job.get("captured_windows"),
                    window_count=job.get("window_count"),
                    failure=job.get("failure"),
                )
            )
    return dict(
        by_automatic_acquisition_name=len(present) + len(missing),
        matched=len(present),
        unmatched=missing,
        raw_names_outside_automatic_name_list=sorted(names - set(present)),
    )


def verify_member(member):
    record = member["raw_recording"]
    segments = [(receipt, json.loads(bound(receipt))) for receipt in record["segments"]]
    stamps, content = [], []
    for _, data in segments:
        if data["kind"] != "short_window_iq_recording":
            raise ValueError("wrong recording format")
        stamps.append(
            (data.get("timing") or {}).get("first_sample_estimate_utc_ns") or data["created_utc_ns"]
        )
        content.extend((c["compressed_sha256"], c["index_sha256"]) for c in data.get("chunks", []))
    actual = (
        digest(json.dumps(sorted(content), separators=(",", ":")).encode())
        if content
        else digest(json.dumps(sorted(entry["sha256"] for entry, _ in segments)).encode())
    )
    if actual != record["identity_sha256"] or min(stamps) != member["captured_utc_ns"]:
        raise ValueError("acquisition identity or time differs: " + member["case_id"])
    recorded_pairs = sorted((c["compressed_sha256"], c["index_sha256"]) for c in record["chunks"])
    if sorted(content) != recorded_pairs or member["window_count"] != sum(
        seg.get("window_count", 0) for _, seg in segments
    ):
        raise ValueError("recording chunk list or window count differs: " + member["case_id"])
    if not START <= min(stamps) < CUTOFF:
        raise ValueError("acquisition outside frozen interval")
    for receipt in (
        member["source_inputs"] + member["tracking_inputs"] + member["recording_metadata"]
    ):
        bound(receipt)
    return actual


def source_root_audit(roots):
    counts = Counter()
    unknown = set()
    files = 0
    for path in sorted((ARCHIVE / "fast-scan-inputs").glob("*.json")):
        files += 1
        for segment in read(path)["segments"]:
            location = Path(segment["path"])
            root = next((p for p in roots if location.is_relative_to(p)), None)
            if root is None:
                unknown.add(str(location))
            else:
                counts[str(root)] += 1
    return dict(
        source_inputs_at_audit=files,
        segment_references_by_root=dict(counts),
        segment_references_outside_census=sorted(unknown),
    )


def verify(output, parent):
    raw = gzip.decompress((output / "manifest.json.gz").read_bytes())
    m = json.loads(raw)
    if (
        m["dataset_id"],
        m["revision"],
        m["parent_manifest_sha256"],
        m["start_utc_ns"],
        m["cutoff_utc_ns"],
    ) != ("DS30", 1, PARENT_SHA, START, CUTOFF):
        raise ValueError("manifest identity or interval changed")
    expected = (output / "manifest.sha256").read_text().split()[0]
    if (
        digest(raw) != expected
        or (output / "manifest.json").exists()
        and (output / "manifest.json").read_bytes() != raw
    ):
        raise ValueError("manifest digest differs")
    for name, sha in read(output / "seal.json")["files"].items():
        if digest((output / name).read_bytes()) != sha:
            raise ValueError("changed release file: " + name)
    rows = m["members"]
    ids = [verify_member(row) for row in rows]
    if len(set(ids)) != len(ids) or set(ids) & {
        x["raw_recording"]["identity_sha256"] for x in parent["members"]
    }:
        raise ValueError("duplicate or parent content overlap")
    labels = [f"DS30-{i:04d}" for i in range(1, len(rows) + 1)]
    cases = [row["case_id"] for row in rows]
    units = read(output / "evaluation-units.json")
    summary = read(output / "membership-summary.json")
    sample = read(output / "sample.json")
    audit = read(output / "discovery.json")
    discovered = {
        p
        for row in rows
        for p in [row["raw_recording"]["root"], *row["raw_recording"]["duplicate_roots"]]
    }
    if (
        len(set(cases)) != len(rows)
        or units["case_ids"] != cases
        or units["dataset_labels"] != labels
        or [row["dataset_label"] for row in rows] != labels
        or [r["case_id"] for r in summary["members"]] != cases
        or [r["case_id"] for r in sample["selected"]] != cases
        or sample["dataset_manifest_sha256"] != expected
        or summary["manifest_sha256"] != expected
        or units["manifest_sha256"] != expected
        or set(audit["selected_fast_roots"]) != discovered
        or audit["errors"]
    ):
        raise ValueError("discovery, evaluation units or summary differ from membership")
    if m["counts"]["members"] != len(rows) or summary["counts"] != m["counts"]:
        raise ValueError("count mismatch")
    return dict(
        verified=True,
        manifest_sha256=expected,
        verified_content_identities=len(ids),
        parent_content_overlap=0,
        source_metadata_rechecked=True,
        discovery_roots=len(audit["roots"]),
        checked_manifests=sum(x["checked_manifests"] for x in audit["roots"]),
        minimum_capture_utc_ns=min(r["captured_utc_ns"] for r in rows),
        maximum_capture_utc_ns=max(r["captured_utc_ns"] for r in rows),
    )


def publish(directory, parent, prior, roots, audit, members):
    rows = prior.pinned.freeze_members(members, parent, CUTOFF, "DS30")
    ledger = audit_ledger(rows)
    recovered = set()
    for job in ledger["unmatched"]:
        # The spool replaces a migrated acquisition with a link to bulk. It can
        # move between the two visits in the global walk. Always check the receipts.
        for base in (
            ARCHIVE / "fast-scan-recordings",
            Path("/srv/postgres-nvme/fast-scan-recordings"),
        ):
            candidate = (base / job["recording_id"]).resolve()
            if candidate.is_dir():
                check, selected = prior.census([candidate], START, CUTOFF)
                if check["errors"]:
                    raise ValueError(check["errors"])
                recovered.update(selected)
    if recovered:
        members = [*members, *prior.collect_members(sorted(recovered), ARCHIVE)]
        rows = prior.pinned.freeze_members(members, parent, CUTOFF, "DS30")
        audit["selected_fast_roots"] = sorted(
            set(audit["selected_fast_roots"]) | set(map(str, recovered))
        )
        ledger = audit_ledger(rows)
    audit["ledger_recovered_fast_roots"] = sorted(map(str, recovered))
    ledger["source_input_root_crosscheck"] = source_root_audit(roots)
    counts = prior.mint.counts(rows)
    counts.update(
        sample_rate_counts=dict(Counter(str(r["sample_rate_hz"]) for r in rows)),
        with_available_glrt_manifest=sum(bool(r["tracking_inputs"]) for r in rows),
    )
    write(directory / "discovery.json", audit)
    write(directory / "ledger.json", ledger)
    manifest = dict(
        schema="post-ds26-recording-membership/v1",
        dataset_id="DS30",
        revision=1,
        created_utc=datetime.now(UTC).isoformat(),
        start_utc_ns=START,
        cutoff_utc_ns=CUTOFF,
        interval="[start_utc_ns, cutoff_utc_ns)",
        parent_dataset="DS29 revision 1",
        parent_manifest_path=str(PRIOR / "dataset/manifest.json"),
        parent_manifest_sha256=PARENT_SHA,
        selection="All discovered whole fast acquisitions ordered by earliest segment and case ID",
        analysis_readiness_required=False,
        complete_recording_required=False,
        scientific_outcomes_used_for_membership=False,
        metadata_snapshot_is_atomic=False,
        payloads_copied_or_rehashed=False,
        discovery_roots=list(map(str, roots)),
        census_privilege=f"uid={os.geteuid()} metadata reads only",
        adapter_deviations=parent["adapter_deviations"],
        inventory_source_sha256={
            str(p): digest(p.read_bytes())
            for p in [
                Path(__file__).resolve(),
                PRIOR / "tooling/freeze_ds29.py",
                *sorted((PRIOR / "tooling/support").glob("*.py")),
            ]
        },
        protocol_sha256=digest((HERE / "PROTOCOL.md").read_bytes()),
        counts=counts,
        members=rows,
    )
    write(directory / "manifest.json", manifest)
    raw = (directory / "manifest.json").read_bytes()
    sha = digest(raw)
    (directory / "manifest.sha256").write_text(sha + "  manifest.json\n")
    (directory / "manifest.json.gz").write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
    keys = (
        "dataset_label",
        "case_id",
        "recording_id",
        "session_id",
        "captured_utc_ns",
        "sample_rate_hz",
        "recording_state",
        "glrt_availability",
    )
    slim = [
        dict(
            {k: r[k] for k in keys},
            mode="fast",
            raw_identity_sha256=r["raw_recording"]["identity_sha256"],
        )
        for r in rows
    ]
    write(
        directory / "membership-summary.json",
        dict(dataset_id="DS30", manifest_sha256=sha, counts=counts, members=slim),
    )
    write(
        directory / "sample.json",
        dict(
            study="DS30",
            dataset_manifest_sha256=sha,
            sampling="all members; unavailable inputs retained",
            selected=[
                dict(
                    {k: v for k, v in row.items() if k != "raw_recording"},
                    mode="fast",
                    raw_identity_sha256=row["raw_recording"]["identity_sha256"],
                    raw_manifest_receipts=row["raw_recording"]["segments"],
                )
                for row in rows
            ],
        ),
    )
    write(
        directory / "evaluation-units.json",
        dict(
            dataset_id="DS30",
            manifest_sha256=sha,
            case_ids=[r["case_id"] for r in rows],
            dataset_labels=[r["dataset_label"] for r in rows],
        ),
    )
    write(
        directory / "seal.json",
        dict(
            files={
                p.name: digest(p.read_bytes())
                for p in sorted(directory.iterdir())
                if p.name != "manifest.json"
            }
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BASE / "dataset")
    parser.add_argument(
        "--cached-inventory",
        type=Path,
        help="Directory with the census and raw inventory from these same DS29 collectors",
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    target = args.output.resolve()
    parent = parent_document()
    if args.verify:
        print(json.dumps(verify(target, parent), indent=2), flush=True)
        return
    if target.exists() or target.is_relative_to("/mnt/qnap01") or target.is_relative_to(ARCHIVE):
        raise ValueError(
            "a fresh local release directory outside the recording archive is required"
        )
    prior = collectors()
    roots = roots_for(prior, parent)
    if args.cached_inventory:
        cached = read(args.cached_inventory / "census.json")
        if (
            cached["start"],
            cached["cutoff"],
            "sha256:" + cached["parent_sha256"],
            cached["roots"],
        ) != (START, CUTOFF, PARENT_SHA, list(map(str, roots))):
            raise ValueError("cached census has a different interval, parent or discovery roots")
        audit = cached["audit"]
        members = read(args.cached_inventory / "member-cache.json")
    else:
        audit, paths = prior.census(roots, START, CUTOFF)
        if audit["errors"]:
            raise ValueError(audit["errors"])
        members = prior.collect_members(paths, ARCHIVE)
    if audit["errors"]:
        raise ValueError(audit["errors"])
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="ds30-freeze-", dir=target.parent))
    try:
        publish(stage, parent, prior, roots, audit, members)
        result = verify(stage, parent)
        write(stage / "verification.json", result)
        # Publish all release files together only after the independent source re-read.
        stage.chmod(0o755)
        os.rename(stage, target)
        print(json.dumps(result), flush=True)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    main()
