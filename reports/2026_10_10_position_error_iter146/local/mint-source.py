"""Metadata-only DS17 mint; all sealed post-DS16 adaptive data, no analysis gate."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = "DS17"
PARENT_DATASET = "DS16"
PARENT = Path("/home/mouse9911/gits/leo-hard60-default/reports/2026_10_08_ds16_last16h")
START = "2026-10-08T01:33:48+00:00"
END = "2026-10-08T14:36:56+00:00"
LOW = int(datetime.fromisoformat(START).timestamp()) * 10**9
HIGH = int(datetime.fromisoformat(END).timestamp()) * 10**9
BULK = Path("/srv/bulk/leo")
SPOOL = Path("/srv/postgres-nvme/leo-scanner-spool")
EVIDENCE = Path("/srv/bulk/leo/v052-adaptive-live")


def configure(dataset, parent_dataset, parent, start, end):
    """Reuse the metadata mint for a successor with a frozen parent boundary."""
    global DATASET, PARENT_DATASET, PARENT, START, END, LOW, HIGH
    low = datetime.fromisoformat(start)
    high = datetime.fromisoformat(end)
    if low.utcoffset() is None or high.utcoffset() is None or low >= high:
        raise ValueError("a nonempty timezone-aware window is required")
    DATASET, PARENT_DATASET, PARENT = dataset, parent_dataset, Path(parent)
    START, END = start, end
    LOW, HIGH = int(low.timestamp()) * 10**9, int(high.timestamp()) * 10**9


def digest(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat()


def eligible(start, finalized):
    return LOW <= start < HIGH and finalized <= HIGH


def completed_archive_evidence(document, sid, rate, serial):
    """Bind a producer archive-completion receipt despite later publication."""
    created = int(datetime.fromisoformat(document["created_at"]).timestamp() * 10**9)
    if (
        document["schema"] != "leo.feature103-dual-rx-adaptive-summary/v1"
        or Path(document["iq_archive"]).name != sid
        or document["rate_hz"] != rate
        or document["radio_serial"] != serial
        or not LOW <= created <= HIGH
    ):
        raise ValueError("archive completion evidence mismatch")
    return created


def merge(published, archives, parent):
    rows = {r["session_id"]: dict(r) for r in published}
    if len(rows) != len(published):
        raise ValueError("duplicate published session")
    for row in archives:
        sid = row["session_id"]
        if sid in rows:
            if rows[sid]["uncompressed_sha256"] != row["uncompressed_sha256"]:
                raise ValueError("archive/published IQ binding mismatch")
            rows[sid].setdefault("archive_references", []).append(row)
        else:
            rows[sid] = dict(row)
    ordered = sorted(rows.values(), key=lambda r: (r["capture_start_utc_ns"], r["session_id"]))
    for key in ("session_id", "uncompressed_sha256"):
        values = [r[key] for r in ordered]
        if len(set(values)) != len(values) or set(values) & {r[key] for r in parent["captures"]}:
            raise ValueError(f"duplicate or parent overlap: {key}")
    for i, row in enumerate(ordered, 1):
        if not eligible(row["capture_start_utc_ns"], row["finalized_utc_ns"]):
            raise ValueError("outside frozen window")
        row["dataset_label"] = f"{DATASET}-{i:03}"
    return ordered


def totals(rows):
    return dict(
        recordings=len(rows),
        visits=sum(r["visits"] for r in rows),
        compressed_bytes=sum(r["compressed_bytes"] for r in rows),
        valid_seconds_per_receiver=sum(r["valid_sample_count"] / r["sample_rate_hz"] for r in rows),
        sample_rate_counts=dict(Counter(str(r["sample_rate_hz"]) for r in rows)),
        source_kind_counts=dict(Counter(r["source_kind"] for r in rows)),
    )


def verify(root):
    seal = json.loads((root / "seal.json").read_bytes())
    for name, expected in seal["files"].items():
        if digest((root / name).read_bytes()) != expected:
            raise ValueError(f"seal mismatch: {name}")
    manifest = json.loads((root / "manifest.json").read_bytes())
    if (
        manifest["dataset_id"] != DATASET
        or manifest["parent_dataset"] != PARENT_DATASET
        or manifest["capture_start_window_utc"] != [START, END]
        or seal["dataset_id"] != DATASET
    ):
        raise ValueError("dataset identity/window mismatch")
    parent = json.loads((root / "parent-manifest.json").read_bytes())
    parent_seal = json.loads((root / "parent-seal.json").read_bytes())
    if (
        digest((root / "parent-manifest.json").read_bytes())
        != parent_seal["files"]["manifest.json"]
    ):
        raise ValueError("parent seal mismatch")
    if parent["capture_start_window_utc"][1] != START:
        raise ValueError("parent boundary mismatch")
    inventory = json.loads((root / "source-inventory.json").read_bytes())
    rows = merge(inventory["published"], inventory["archives"], parent)
    if rows != manifest["captures"] or totals(rows) != manifest["counts"]:
        raise ValueError("membership/count mismatch")
    if manifest["parent_manifest_sha256"] != digest((root / "parent-manifest.json").read_bytes()):
        raise ValueError("parent reference mismatch")
    units = json.loads((root / "evaluation-units.json").read_bytes())
    if units["full"] != [r["session_id"] for r in rows] or units["singles"] != [
        [r["session_id"]] for r in rows
    ]:
        raise ValueError("evaluation membership mismatch")
    if units["manifest_sha256"] != digest((root / "manifest.json").read_bytes()):
        raise ValueError("evaluation manifest mismatch")
    for row in inventory["published"] + inventory["archives"]:
        if (
            digest((root / row["metadata_snapshot"]).read_bytes())
            != row["metadata_snapshot_sha256"]
        ):
            raise ValueError("source snapshot mismatch")
        completion = row.get("pre_cutoff_archive_completion_evidence")
        if completion:
            source = json.loads((root / row["metadata_snapshot"]).read_bytes())
            ns = completed_archive_evidence(
                json.loads((root / completion).read_bytes()),
                row["session_id"],
                row["sample_rate_hz"],
                source["receipt"]["radio_serial"],
            )
            if ns != row["finalized_utc_ns"] or source["timing"]["terminal_realtime_ns"] > HIGH:
                raise ValueError("completion time mismatch")
    return {
        "verified": DATASET,
        **manifest["counts"],
        "partial_records": len(inventory["partials"]),
        "excluded_records": len(inventory["excluded"]),
    }


def mint(output):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    output.mkdir(parents=True, exist_ok=False)
    (output / "metadata").mkdir()
    for name in ("manifest.json", "seal.json"):
        (output / ("parent-" + name)).write_bytes((PARENT / name).read_bytes())
    parent = json.loads((output / "parent-manifest.json").read_bytes())
    parent_seal = json.loads((output / "parent-seal.json").read_bytes())
    if (
        digest((output / "parent-manifest.json").read_bytes())
        != parent_seal["files"]["manifest.json"]
    ):
        raise ValueError("parent seal mismatch")
    if parent["capture_start_window_utc"][1] != START:
        raise ValueError("parent boundary mismatch")
    (output / "mint-source.py").write_bytes(Path(__file__).read_bytes())
    (output / "test-source.py").write_bytes((HERE / "test_mint.py").read_bytes())
    published, archives, excluded, partials = [], [], [], []
    started = datetime.now(UTC).isoformat()
    store = AdaptiveHopIqStore(BULK, read_only=True)
    try:
        index = sorted((ns, sid) for ns, sid in store.history_index() if LOW <= ns < HIGH)
        write(
            output / "candidate-index.json",
            {
                "observed_utc": started,
                "source": "AdaptiveHopIqStore.history_index",
                "candidates": [
                    {"capture_start_utc_ns": ns, "session_id": sid} for ns, sid in index
                ],
            },
        )
        for ns, sid in index:
            capture = store.inspect(sid)
            m, r = capture.manifest, capture.manifest.receipt
            if (m.timing.first_sample_estimate_utc_ns if m.timing else m.created_utc_ns) != ns:
                raise ValueError("index timing mismatch")
            membership_seal_ns = m.finalized_utc_ns
            completion_reference = None
            if not eligible(ns, membership_seal_ns):
                evidence_paths = list(EVIDENCE.glob(f"*-{sid}.json"))
                if len(evidence_paths) != 1 or not m.timing or m.timing.terminal_realtime_ns > HIGH:
                    excluded.append(
                        {
                            "session_id": sid,
                            "source_kind": "published",
                            "reason": "no_pre_cutoff_archive_completion_evidence",
                        }
                    )
                    continue
                evidence_bytes = evidence_paths[0].read_bytes()
                membership_seal_ns = completed_archive_evidence(
                    json.loads(evidence_bytes), sid, r.plan.geometry.sample_rate_hz, r.radio_serial
                )
                completion_reference = f"metadata/completion-{sid}.json"
                (output / completion_reference).write_bytes(evidence_bytes)
            snapshot = f"metadata/published-{sid}.json"
            payload = m.model_dump_json(indent=2).encode() + b"\n"
            (output / snapshot).write_bytes(payload)
            published.append(
                dict(
                    session_id=sid,
                    source_kind="published",
                    capture_start_utc_ns=ns,
                    finalized_utc_ns=membership_seal_ns,
                    published_finalized_utc_ns=m.finalized_utc_ns,
                    pre_cutoff_archive_completion_evidence=completion_reference,
                    time_basis="first-sample estimate"
                    if m.timing
                    else "manifest created time fallback",
                    recording_manifest_sha256=capture.manifest_sha256,
                    metadata_snapshot=snapshot,
                    metadata_snapshot_sha256=digest(payload),
                    uncompressed_sha256=m.uncompressed_sha256,
                    sample_rate_hz=r.plan.geometry.sample_rate_hz,
                    visits=r.complete_visit_count,
                    valid_sample_count=r.valid_sample_count,
                    compressed_bytes=m.compressed_bytes,
                    transport_missing_sample_count=r.transport_missing_sample_count,
                    unclassified_sample_count=r.unclassified_sample_count,
                    unreceived_tail_sample_count=r.unreceived_tail_sample_count,
                    terminal=r.terminal.model_dump(mode="json"),
                    restoration=r.restoration.model_dump(mode="json"),
                    timing=m.timing.model_dump(mode="json") if m.timing else None,
                    raw_iq_reference={"store_root": str(BULK), "session_id": sid},
                )
            )
            print("published", len(published), sid, flush=True)
    finally:
        store.close()
    # Firmware archive manifests are a public interchange format. No import,
    # publication, payload reads, or spool mutation is performed.
    spool_inventory = []
    for source_root in sorted(SPOOL.iterdir()):
        if not source_root.is_dir():
            continue
        for directory in sorted(source_root.iterdir()):
            if not directory.is_dir():
                continue
            path = directory / "manifest.json"
            if not path.exists():
                stats = [(p.name, p.stat()) for p in directory.iterdir() if p.is_file()]
                if stats and LOW <= min(s.st_mtime_ns for _, s in stats) < HIGH:
                    partials.append(
                        dict(
                            path=str(directory),
                            status="unsealed_not_evaluable",
                            time_basis="file mtimes, no sealed capture timing",
                            files=len(stats),
                            bytes_observed=sum(s.st_size for _, s in stats),
                            first_file_mtime_utc_ns=min(s.st_mtime_ns for _, s in stats),
                            last_file_mtime_utc_ns=max(s.st_mtime_ns for _, s in stats),
                        )
                    )
                continue
            payload = path.read_bytes()
            d = json.loads(payload)
            if d.get("schema") != "org.leo.firmware-adaptive-iq/v1":
                spool_inventory.append(
                    {"path": str(path), "schema": d.get("schema"), "status": "other_format"}
                )
                continue
            timing = d.get("evidence", {}).get("utc_timing")
            if not timing:
                if d["created_utc_ns"] >= LOW:
                    raise ValueError(f"potentially recent archive lacks timing: {path}")
                spool_inventory.append(
                    {
                        "path": str(path),
                        "status": "pre-window seal, no timing",
                        "created_utc_ns": d["created_utc_ns"],
                    }
                )
                continue
            ns = timing["begin_before_realtime_ns"]
            spool_inventory.append({"path": str(path), "capture_start_utc_ns": ns})
            if not LOW <= ns < HIGH:
                continue
            sid = d["session_id"]
            if directory.name != sid:
                raise ValueError("archive session/path mismatch")
            if not eligible(ns, d["created_utc_ns"]):
                excluded.append(
                    {
                        "session_id": sid,
                        "source_kind": "firmware_archive",
                        "reason": "sealed_after_cutoff",
                    }
                )
                continue
            retained = [v for v in d["visits"] if v["iq"] is not None]
            snapshot = f"metadata/archive-{sid}.json"
            (output / snapshot).write_bytes(payload)
            archives.append(
                dict(
                    session_id=sid,
                    source_kind="firmware_archive",
                    capture_start_utc_ns=ns,
                    finalized_utc_ns=d["created_utc_ns"],
                    time_basis="host begin-before bracket, not qualified first sample",
                    source_manifest_path=str(path),
                    metadata_snapshot=snapshot,
                    metadata_snapshot_sha256=digest(payload),
                    uncompressed_sha256=d["uncompressed_sha256"],
                    sample_rate_hz=d["setup"]["source_rate_hz"],
                    visits=len(retained),
                    skipped_visits=len(d["visits"]) - len(retained),
                    valid_sample_count=sum(
                        v["record"]["valid_end"] - v["record"]["valid_start"] for v in retained
                    ),
                    compressed_bytes=sum(v["iq"]["compressed_bytes"] for v in retained),
                    terminal=d["terminal"],
                    receiver_ids=d["physical_receivers"],
                )
            )
    rows = merge(published, archives, parent)
    write(
        output / "source-inventory.json",
        dict(
            published=published,
            archives=archives,
            excluded=excluded,
            partials=partials,
            spool_manifest_inventory=spool_inventory,
            spool_root=str(SPOOL),
            observed_start_utc=started,
            observed_end_utc=datetime.now(UTC).isoformat(),
        ),
    )
    write(
        output / "manifest.json",
        dict(
            dataset_id=DATASET,
            status="minted",
            parent_dataset=PARENT_DATASET,
            parent_manifest_sha256=digest((output / "parent-manifest.json").read_bytes()),
            capture_start_window_utc=[START, END],
            window_rule="start inclusive, end exclusive; sealed by end",
            membership_rule=(
                "All sealed adaptive recordings discovered in published store and "
                "firmware spool; analysis readiness and capture-quality flags "
                "do not gate membership."
            ),
            temporal_scope=(
                f"{PARENT_DATASET} window endpoint, not its last admitted capture end. "
                "Whole recordings only; no slicing."
            ),
            inventory_finished_utc=datetime.now(UTC).isoformat(),
            counts=totals(rows),
            captures=rows,
            excluded_candidates=excluded,
            incomplete_recordings=partials,
            source_runtime=str(Path("/opt/leo-tracker/current-api").resolve()),
            limitations=[
                "Metadata and source seals checked; raw IQ not copied, read or rehashed.",
                "Live inventory is not atomic; availability can change during collection.",
                "Archive times use host brackets; partials have only file mtime evidence.",
                "Analysis readiness not evaluated. No retention hold or backup created.",
            ],
        ),
    )
    write(
        output / "evaluation-units.json",
        dict(
            manifest_sha256=digest((output / "manifest.json").read_bytes()),
            full=[r["session_id"] for r in rows],
            singles=[[r["session_id"]] for r in rows],
            note="Whole recordings, both receivers together; no training split or model selection.",
        ),
    )
    write(
        output / "seal.json",
        dict(
            dataset_id=DATASET,
            files={
                str(p.relative_to(output)): digest(p.read_bytes())
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
        ),
    )
    print(json.dumps(verify(output), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("mint", "verify"))
    parser.add_argument("--output", type=Path, default=HERE / "local")
    parser.add_argument("--dataset-id", default=DATASET)
    parser.add_argument("--parent-dataset", default=PARENT_DATASET)
    parser.add_argument("--parent", type=Path, default=PARENT)
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()
    configure(args.dataset_id, args.parent_dataset, args.parent, args.start, args.end)
    if args.action == "mint":
        mint(args.output)
    else:
        print(json.dumps(verify(args.output), indent=2))
