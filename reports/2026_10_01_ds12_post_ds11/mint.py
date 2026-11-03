"""Freeze all post-DS11 adaptive recordings, independent of analysis readiness.

Run collect with the installed API Python and read access to both source stores.
No capture, publication, analysis, deletion or raw-IQ copy is performed.
"""
import argparse
from collections import Counter
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE / "local"
PARENT_DIR = SOURCE.parent / "2026_09_30_ds11_post_ds10"
PARENT = PARENT_DIR / "local/manifest.json"
BULK = Path("/srv/bulk/leo")
SPOOL = Path("/srv/postgres-nvme/leo-scanner-spool/v052-adaptive")
CUTOFF = 1790815191000000000  # 2026-10-01 00:39:51 UTC, initial request inventory


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat()


def in_window(start, lower, cutoff=CUTOFF):
    return lower < start <= cutoff


def archive_row(document, path, payload):
    """Read the public firmware archive document without importing/publishing IQ."""
    assert document["schema"] == "org.leo.firmware-adaptive-iq/v1"
    assert document["session_id"] == path.parent.name
    visits = document["visits"]
    retained = [v for v in visits if v["iq"] is not None]
    timing = document["evidence"]["utc_timing"]
    rate = document["setup"]["source_rate_hz"]
    reasons = []
    terminal = document["terminal"]
    if terminal["error"] or terminal["cancelled"] or terminal["state"] != 1:
        reasons.append("capture_terminal_not_complete")
    if terminal["delivered"] != len(retained):
        reasons.append("visit_count_mismatch")
    if len(retained) != len(visits):
        reasons.append("skipped_visits_without_iq")
    if any(v["record"]["missing_samples_before"] for v in visits):
        reasons.append("missing_samples")
    return dict(
        session_id=document["session_id"], source_kind="firmware_archive",
        source_manifest_path=str(path), manifest_sha256=digest(payload),
        capture_start_utc_ns=timing["begin_before_realtime_ns"],
        capture_end_utc_ns=timing["terminal_realtime_ns"],
        time_basis="host begin-before / terminal brackets; not a qualified first-sample estimate",
        finalized_utc_ns=document["created_utc_ns"],
        sample_rate_hz=rate, receiver_ids=document["physical_receivers"],
        visits=len(retained), scheduled_visits=len(visits), skipped_visits=len(visits)-len(retained),
        compressed_bytes=sum(v["iq"]["compressed_bytes"] for v in retained),
        valid_sample_count=sum(v["record"]["valid_end"] - v["record"]["valid_start"] for v in retained),
        uncompressed_sha256=document["uncompressed_sha256"],
        capture_quality_reasons=reasons,
        analysis_ready_at_cutoff=False,
        analysis_reasons=["not_published_at_inventory"],
    )


def merge_sources(published, archived):
    rows = {r["session_id"]: dict(r) for r in published}
    assert len(rows) == len(published)
    for row in archived:
        sid = row["session_id"]
        if sid in rows:
            assert rows[sid]["uncompressed_sha256"] == row["uncompressed_sha256"]
            rows[sid]["archive_manifest_sha256"] = row["manifest_sha256"]
        else:
            rows[sid] = dict(row)
    return sorted(rows.values(), key=lambda r: (r["capture_start_utc_ns"], r["session_id"]))


def totals(rows):
    return dict(recordings=len(rows), visits=sum(r["visits"] for r in rows),
                compressed_bytes=sum(r["compressed_bytes"] for r in rows),
                active_seconds_per_receiver=sum(r["valid_sample_count"] / r["sample_rate_hz"] for r in rows),
                sample_rate_counts=dict(Counter(str(r["sample_rate_hz"]) for r in rows)),
                source_kind_counts=dict(Counter(r["source_kind"] for r in rows)),
                analysis_ready_at_cutoff=sum(r["analysis_ready_at_cutoff"] for r in rows))


def collect():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    assert not (ROOT / "manifest.json").exists(), "DS12 is already sealed"
    ROOT.mkdir(exist_ok=True)
    for name in ("analysis", "archives", "published"):
        (ROOT / name).mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("ds11_reader", PARENT_DIR / "mint.py")
    ds11 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ds11)
    parent = json.loads(PARENT.read_bytes())
    lower = max(r["capture_end_utc_ns"] for r in parent["captures"])
    store = AdaptiveHopIqStore(BULK, read_only=True)
    published = []
    try:
        index = store.tracking_metadata_index()
        write(ROOT / "published-index.json", index)
        for _, captured, _, sid in sorted(index, key=lambda r: (r[1], r[3])):
            if not in_window(captured, lower):
                continue
            row = ds11.inspect(store, sid, lower, CUTOFF)
            session = store.inspect(sid)
            write(ROOT / "published" / (sid + ".json"), session.manifest.model_dump(mode="json"))
            row["metadata_snapshot_sha256"] = digest((ROOT / "published" / (sid + ".json")).read_bytes())
            row["source_kind"] = "published"
            row["capture_quality_reasons"] = row.pop("exclusion_reasons")
            evidence_path = ROOT / "analysis" / (sid + ".json")
            evidence = json.loads(evidence_path.read_bytes()) if evidence_path.exists() else {"observed_utc": utc(time.time_ns())}
            for name, route in {
                "glrt": f"/api/v2/scanner/adaptive-sessions/{sid}/analysis?probe_stride_ms=120",
                "tracking": f"/api/v1/scanner/tracking/{sid}",
            }.items():
                if name in evidence:
                    continue
                try:
                    with urlopen("http://127.0.0.1:8090" + route, timeout=15) as response:
                        evidence[name] = json.load(response)
                except (HTTPError, URLError, TimeoutError) as error:
                    evidence[name] = {"request_error": str(error)}
            write(evidence_path, evidence)
            row["analysis_evidence_sha256"] = digest(evidence_path.read_bytes())
            row["analysis_reasons"] = ds11.analysis_reasons(row, evidence["glrt"], evidence["tracking"], CUTOFF)
            row["analysis_ready_at_cutoff"] = not row["analysis_reasons"]
            published.append(row)
            print("Published", len(published), sid, flush=True)
    finally:
        store.close()
    archived, incomplete = [], []
    for directory in sorted(SPOOL.iterdir()):
        if not directory.is_dir():
            continue
        path = directory / "manifest.json"
        if path.exists():
            payload = path.read_bytes()
            document = json.loads(payload)
            start = document.get("evidence", {}).get("utc_timing", {}).get("begin_before_realtime_ns")
            if start is None or not in_window(start, lower):
                continue
            row = archive_row(document, path, payload)
            (ROOT / "archives" / (row["session_id"] + ".json")).write_bytes(payload)
            if row["finalized_utc_ns"] > CUTOFF:
                row["capture_quality_reasons"].append("sealed_after_cutoff")
            # Check presence and lengths only; do not decompress or hash terabytes.
            missing = []
            for visit in document["visits"]:
                if visit["iq"] is None:
                    continue
                relative = visit["iq"]["relative_path"]
                assert Path(relative).name == relative
                chunk = directory / relative
                if not chunk.is_file() or chunk.stat().st_size != visit["iq"]["compressed_bytes"]:
                    missing.append(relative)
            row["missing_or_wrong_size_chunks"] = missing
            if missing:
                row["capture_quality_reasons"].append("archive_chunk_presence_or_size_failure")
            archived.append(row)
        else:
            files = [p for p in directory.iterdir() if p.is_file()]
            stamps = [p.stat().st_mtime_ns for p in files]
            if stamps and in_window(min(stamps), lower):
                incomplete.append(dict(path=str(directory), session_id=directory.name.removeprefix(".").removesuffix(".partial"),
                                       status="unsealed_partial_not_evaluable", files=len(files),
                                       stored_bytes=sum(p.stat().st_size for p in files),
                                       first_file_mtime_utc_ns=min(stamps), last_file_mtime_utc_ns=max(stamps),
                                       time_basis="file mtimes only; no sealed timing authority"))
    captures = merge_sources(published, archived)
    parent_ids = {r["session_id"] for r in parent["captures"]}
    assert not parent_ids & {r["session_id"] for r in captures}
    write(ROOT / "source-inventory.json", {"published": published, "archives": archived, "incomplete": incomplete})
    manifest = dict(schema="ds12-recordings/v1", dataset_id="DS12", status="minted",
                    parent_dataset="DS11", parent_manifest_sha256=digest(PARENT.read_bytes()),
                    after_parent_capture_end_utc_ns=lower, inventory_cutoff_utc_ns=CUTOFF,
                    inventory_cutoff_utc=utc(CUTOFF), inventory_finished_utc=utc(time.time_ns()),
                    membership_policy="All sealed adaptive recordings starting after the last DS11 capture through cutoff; published and firmware archives deduplicated by session ID. Analysis readiness does not gate membership. Unsealed partials are retained separately.",
                    integrity_scope="Public metadata validation; firmware archive chunk presence/size checked. Raw IQ is not copied, decompressed or rehashed. API readiness observed during inventory; tracking creation bounded by cutoff.",
                    storage_reader_release=str(Path("/opt/leo-tracker/current-api").resolve()),
                    retention={"enforced_hold": False, "payload_copied": False},
                    counts=totals(captures), captures=captures, incomplete_recordings=incomplete,
                    recovered_ds11_excluded=sorted({r["session_id"] for r in parent["excluded"]} & {r["session_id"] for r in captures}))
    write(ROOT / "manifest.json", manifest)
    ids = [r["session_id"] for r in captures]
    write(ROOT / "evaluation-units.json", dict(
        manifest_sha256=digest((ROOT / "manifest.json").read_bytes()),
        full=ids, singles=[[sid] for sid in ids], groups_of_eight=[ids[i:i+8] for i in range(0,len(ids)-7,8)],
        remainder=ids[len(ids)//8*8:],
        analysis_ready=[r["session_id"] for r in captures if r["analysis_ready_at_cutoff"] and not r["capture_quality_reasons"]],
        note="Full membership is not an assertion of analysis readiness; use analysis_ready for DS11-compatible evaluations."))
    paths = sorted(ROOT.rglob("*.json")) + [SOURCE / "mint.py", SOURCE / "test_mint.py", PARENT_DIR / "mint.py"]
    import os
    (ROOT / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())[7:]}  {os.path.relpath(p, ROOT)}\n" for p in paths))
    verify()


def verify():
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert digest((ROOT / name).read_bytes()) == "sha256:" + expected, name
    m = json.loads((ROOT / "manifest.json").read_bytes())
    parent = json.loads(PARENT.read_bytes())
    assert m["parent_manifest_sha256"] == digest(PARENT.read_bytes())
    assert m["after_parent_capture_end_utc_ns"] == max(r["capture_end_utc_ns"] for r in parent["captures"])
    inventory = json.loads((ROOT / "source-inventory.json").read_bytes())
    assert m["captures"] == merge_sources(inventory["published"], inventory["archives"])
    assert m["incomplete_recordings"] == inventory["incomplete"]
    assert m["counts"] == totals(m["captures"])
    for key in ("session_id", "uncompressed_sha256"):
        values = {r[key] for r in m["captures"]}
        assert len(values) == len(m["captures"])
        assert not values & {r[key] for r in parent["captures"]}
    for row in m["captures"]:
        assert in_window(row["capture_start_utc_ns"], m["after_parent_capture_end_utc_ns"], m["inventory_cutoff_utc_ns"])
    units = json.loads((ROOT / "evaluation-units.json").read_bytes())
    assert units["manifest_sha256"] == digest((ROOT / "manifest.json").read_bytes())
    assert units["full"] == [r["session_id"] for r in m["captures"]]
    assert sum(units["groups_of_eight"], []) + units["remainder"] == units["full"]
    assert units["analysis_ready"] == [r["session_id"] for r in m["captures"] if r["analysis_ready_at_cutoff"] and not r["capture_quality_reasons"]]
    print(json.dumps({"verified": "DS12", **m["counts"], "incomplete_recordings": len(m["incomplete_recordings"])}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("collect", "verify"))
    globals()[parser.parse_args().action]()
