"""Freeze DS13 from the requested scan, using existing complete production analysis.

Collection uses the installed read-only storage port and GET status endpoints.
No capture, publication, analysis, or raw-IQ copy is launched.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import urlopen

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE / "local"
ADMISSION_SOURCE = SOURCE.parent / "2026_09_30_ds11_post_ds10/mint.py"
PARENT = SOURCE.parent / "2026_10_01_ds12_post_ds11/local/manifest.json"
ANCHOR = "scan-fw-911c4e5db9243281"
# First inventory inspection for this request: 2026-10-02 16:46:54 UTC.
CUTOFF = 1790959614000000000

spec = importlib.util.spec_from_file_location("ds13_admission", ADMISSION_SOURCE)
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)
digest, write, utc = admission.digest, admission.write, admission.utc


def candidates(index, lower, cutoff):
    """Capture-time order, with both the requested start and cutoff inclusive."""
    result = sorted(
        (list(row) for row in index if lower <= row[1] <= cutoff),
        key=lambda row: (row[1], row[3]),
    )
    assert len({row[3] for row in result}) == len(result), "Duplicate session ID"
    return result


def require_unsealed():
    if (ROOT / "manifest.json").exists():
        raise RuntimeError("DS13 already sealed; refusing to overwrite")


def read_status(route):
    try:
        with urlopen("http://127.0.0.1:8090" + route, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code != 404:
            raise  # An unavailable API must not silently exclude a complete scan.
        return {"request_error": str(error), "http_status": error.code}


def collect():
    require_unsealed()
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    ROOT.mkdir(exist_ok=True)
    (ROOT / "analysis").mkdir(exist_ok=True)
    (ROOT / "published").mkdir(exist_ok=True)
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        snapshot_path = ROOT / "candidate-index.json"
        if not snapshot_path.exists():
            anchor = store.inspect(ANCHOR)
            timing = anchor.manifest.timing
            assert timing and timing.qualified
            index = store.tracking_metadata_index()
            selected = candidates(index, timing.first_sample_estimate_utc_ns, CUTOFF)
            assert any(row[3] == ANCHOR for row in selected)
            write(snapshot_path, dict(
                cutoff=CUTOFF,
                start_session_id=ANCHOR,
                start_manifest_sha256=anchor.manifest_sha256,
                lower_inclusive=timing.first_sample_estimate_utc_ns,
                lower_earliest=timing.first_sample_earliest_utc_ns,
                candidates=selected,
                published_index=[list(row) for row in index],
                observed_utc=utc(time.time_ns()),
                parent_manifest_sha256=digest(PARENT.read_bytes()),
                admission_source_sha256=digest(ADMISSION_SOURCE.read_bytes()),
                storage_reader_release=str(Path("/opt/leo-tracker/current-api").resolve()),
            ))
        snapshot = json.loads(snapshot_path.read_bytes())
        assert snapshot["admission_source_sha256"] == digest(ADMISSION_SOURCE.read_bytes())
        assert snapshot["parent_manifest_sha256"] == digest(PARENT.read_bytes())
        inventory_path = ROOT / "inventory.json"
        rows = json.loads(inventory_path.read_bytes()) if inventory_path.exists() else []
        assert [row["session_id"] for row in rows] == [row[3] for row in snapshot["candidates"][:len(rows)]]
        started = time.monotonic()
        for _, _, _, sid in snapshot["candidates"][len(rows):]:
            if time.monotonic() - started > 40:
                break
            row = admission.inspect(store, sid, snapshot["lower_earliest"] - 1, snapshot["cutoff"])
            row["capture_quality_reasons"] = row.pop("exclusion_reasons")
            session = store.inspect(sid)
            assert session.manifest_sha256 == row["manifest_sha256"]
            metadata_path = ROOT / "published" / (sid + ".json")
            write(metadata_path, session.manifest.model_dump(mode="json"))
            row["metadata_snapshot_sha256"] = digest(metadata_path.read_bytes())
            evidence = {"observed_utc": utc(time.time_ns())}
            evidence["glrt"] = read_status(f"/api/v2/scanner/adaptive-sessions/{sid}/analysis?probe_stride_ms=120")
            evidence["tracking"] = read_status(f"/api/v1/scanner/tracking/{sid}")
            evidence["finished_utc"] = utc(time.time_ns())
            evidence_path = ROOT / "analysis" / (sid + ".json")
            write(evidence_path, evidence)
            row["analysis_evidence_sha256"] = digest(evidence_path.read_bytes())
            row["analysis_reasons"] = admission.analysis_reasons(row, evidence["glrt"], evidence["tracking"], snapshot["cutoff"])
            row["exclusion_reasons"] = row["capture_quality_reasons"] + row["analysis_reasons"]
            rows.append(row)
            write(inventory_path, rows)
            print(f"Inspected {len(rows)}/{len(snapshot['candidates'])}: {sid} {row['exclusion_reasons']}", flush=True)
    finally:
        store.close()
    print("Inventory complete; ready to seal" if len(rows) == len(snapshot["candidates"]) else "Checkpoint saved; rerun collect", flush=True)


def validate_inventory(snapshot, rows):
    assert snapshot["start_session_id"] == ANCHOR
    assert snapshot["cutoff"] == CUTOFF
    assert snapshot["parent_manifest_sha256"] == digest(PARENT.read_bytes())
    assert snapshot["admission_source_sha256"] == digest(ADMISSION_SOURCE.read_bytes())
    assert snapshot["candidates"] == candidates(snapshot["published_index"], snapshot["lower_inclusive"], snapshot["cutoff"])
    assert [row["session_id"] for row in rows] == [row[3] for row in snapshot["candidates"]]
    anchor = next(row for row in rows if row["session_id"] == ANCHOR)
    assert anchor["manifest_sha256"] == snapshot["start_manifest_sha256"]
    assert anchor["capture_start_utc_ns"] == snapshot["lower_inclusive"]
    assert anchor["capture_start_earliest_utc_ns"] == snapshot["lower_earliest"]
    for indexed, row in zip(snapshot["candidates"], rows, strict=True):
        assert row["capture_start_utc_ns"] == indexed[1]
        payload = (ROOT / "analysis" / (row["session_id"] + ".json")).read_bytes()
        assert digest(payload) == row["analysis_evidence_sha256"]
        evidence = json.loads(payload)
        assert row["analysis_reasons"] == admission.analysis_reasons(row, evidence["glrt"], evidence["tracking"], snapshot["cutoff"])
        assert row["exclusion_reasons"] == row["capture_quality_reasons"] + row["analysis_reasons"]
        metadata = (ROOT / "published" / (row["session_id"] + ".json")).read_bytes()
        assert digest(metadata) == row["metadata_snapshot_sha256"]
        assert json.loads(metadata)["session_id"] == row["session_id"]
        if not row["exclusion_reasons"]:
            assert row["utc_qualified"]
            assert row["capture_start_earliest_utc_ns"] >= snapshot["lower_earliest"]
            assert row["capture_start_utc_ns"] <= row["capture_end_utc_ns"] <= row["finalized_utc_ns"] <= snapshot["cutoff"]


def evaluation_units(manifest):
    rows = manifest["captures"]
    ids = [row["session_id"] for row in rows]
    return dict(
        schema="ds13-evaluation-units/v1",
        manifest_sha256=digest((ROOT / "manifest.json").read_bytes()),
        full=ids, singles=[[sid] for sid in ids],
        groups_of_eight=[ids[i:i + 8] for i in range(0, len(ids) - 7, 8)],
        remainder=ids[len(ids) // 8 * 8:],
        rate_strata={rate: [r["session_id"] for r in rows if str(r["sample_rate_hz"]) == rate] for rate in manifest["counts"]["sample_rate_counts"]},
        note="Chronological evaluation views, not train/test partitions; excluded scans can create gaps.",
    )


def seal():
    require_unsealed()
    snapshot = json.loads((ROOT / "candidate-index.json").read_bytes())
    rows = json.loads((ROOT / "inventory.json").read_bytes())
    validate_inventory(snapshot, rows)
    admitted = [row for row in rows if not row["exclusion_reasons"]]
    assert admitted, "Refusing to mint an empty dataset"
    assert any(row["session_id"] == ANCHOR for row in admitted), "Requested starting scan is not complete"
    parent = json.loads(PARENT.read_bytes())
    for key in ("session_id", "manifest_sha256", "uncompressed_sha256"):
        assert len({row[key] for row in admitted}) == len(admitted)
        assert not {row[key] for row in admitted} & {row[key] for row in parent["captures"]}
    manifest = dict(
        schema="ds13-admission/v1", dataset_id="DS13", status="minted",
        start_session_id=ANCHOR, start_inclusive=True,
        from_capture_start_utc_ns=snapshot["lower_inclusive"],
        inventory_cutoff_utc_ns=snapshot["cutoff"], inventory_cutoff_utc=utc(snapshot["cutoff"]),
        inventory_finished_utc=utc(time.time_ns()),
        parent_dataset="DS12", parent_manifest_sha256=snapshot["parent_manifest_sha256"],
        storage_reader_release=snapshot["storage_reader_release"],
        membership_policy="All published adaptive scans at or after the requested scan's capture start, through cutoff, passing complete-capture and complete-production-analysis admission. No rate or scientific-result filtering.",
        analysis_policy="Complete 120 ms-stride GLRT visit coverage and exact raw -> GLRT -> tracking binding; complete trajectory/TLE product created by cutoff. Production group limits and deferred groups are allowed and preserved. Readiness observed over the inventory interval, not an atomic database snapshot.",
        integrity_scope="Published metadata validated through the read-only storage port; metadata and API responses preserved and hashed. Raw IQ not copied, decompressed, or rehashed; chunk presence not independently checked.",
        retention=dict(enforced_hold=False, payload_copied=False),
        counts=admission.totals(admitted), captures=admitted,
        excluded=[row for row in rows if row["exclusion_reasons"]],
    )
    write(ROOT / "manifest.json", manifest)
    write(ROOT / "evaluation-units.json", evaluation_units(manifest))
    paths = sorted(ROOT.rglob("*.json")) + [SOURCE / "mint.py", SOURCE / "test_mint.py", ADMISSION_SOURCE, PARENT]
    (ROOT / "SHA256SUMS").write_text("".join(f"{digest(path.read_bytes())[7:]}  {os.path.relpath(path, ROOT)}\n" for path in paths))
    verify()


def verify():
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert digest((ROOT / name).read_bytes()) == "sha256:" + expected, name
    manifest = json.loads((ROOT / "manifest.json").read_bytes())
    snapshot = json.loads((ROOT / "candidate-index.json").read_bytes())
    rows = json.loads((ROOT / "inventory.json").read_bytes())
    validate_inventory(snapshot, rows)
    assert manifest["dataset_id"] == "DS13" and manifest["status"] == "minted"
    assert manifest["start_session_id"] == ANCHOR and manifest["start_inclusive"] is True
    assert manifest["from_capture_start_utc_ns"] == snapshot["lower_inclusive"]
    assert manifest["inventory_cutoff_utc_ns"] == snapshot["cutoff"]
    assert manifest["parent_dataset"] == "DS12"
    assert manifest["parent_manifest_sha256"] == snapshot["parent_manifest_sha256"]
    assert manifest["captures"] == [row for row in rows if not row["exclusion_reasons"]]
    assert manifest["excluded"] == [row for row in rows if row["exclusion_reasons"]]
    assert any(row["session_id"] == ANCHOR for row in manifest["captures"])
    assert manifest["counts"] == admission.totals(manifest["captures"])
    parent = json.loads(PARENT.read_bytes())
    for key in ("session_id", "manifest_sha256", "uncompressed_sha256"):
        values = {row[key] for row in manifest["captures"]}
        assert len(values) == len(manifest["captures"])
        assert not values & {row[key] for row in parent["captures"]}
    assert json.loads((ROOT / "evaluation-units.json").read_bytes()) == evaluation_units(manifest)
    print(json.dumps(dict(verified="DS13", **manifest["counts"], excluded=len(manifest["excluded"])), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("collect", "seal", "verify"))
    globals()[parser.parse_args().action]()
