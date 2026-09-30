"""Read-only DS10 admission and offline verification; no analysis is launched."""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE / "local"
PARENT = SOURCE.parent / "2026_09_28_ds9_post_ds8/manifest.json"
BULK = Path("/srv/bulk/leo")


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat()


def analysis_reasons(row, glrt, tracking, cutoff):
    """Admit completed production analysis with an exact raw -> GLRT -> tracking chain."""
    reasons = []
    product = tracking.get("product") or {}
    if glrt.get("state") not in ("metrics_ready", "figures_ready"):
        reasons.append("glrt_incomplete")
    if glrt.get("total_visits") != row["visits"] or glrt.get("checkpoint_visits") != row["visits"]:
        reasons.append("glrt_visit_coverage_incomplete")
    if glrt.get("configuration", {}).get("probe_stride_ms") != 120:
        reasons.append("wrong_glrt_configuration")
    if (
        glrt.get("session_id") != row["session_id"]
        or glrt.get("input_manifest_sha256") != row["manifest_sha256"]
        or not glrt.get("metrics_manifest_sha256")
        or not glrt.get("binding_sha256")
    ):
        reasons.append("glrt_binding_invalid")
    if tracking.get("state") != "complete":
        reasons.append("tracking_incomplete")
    if (
        tracking.get("session_id") != row["session_id"]
        or product.get("session_id") != row["session_id"]
        or product.get("input_manifest_sha256") != row["manifest_sha256"]
        or product.get("analysis_manifest_sha256") != glrt.get("metrics_manifest_sha256")
        or not product.get("configuration_digest")
    ):
        reasons.append("tracking_binding_invalid")
    if product.get("trajectory_state") != "complete" or product.get("tle_state") != "complete":
        reasons.append("tracking_stages_incomplete")
    try:
        created = datetime.fromisoformat(product["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None or int(created.timestamp() * 1e9) > cutoff:
            reasons.append("tracking_not_complete_at_cutoff")
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.append("tracking_completion_time_unavailable")
    return reasons


def inspect(store, sid, lower, cutoff):
    session = store.inspect(sid)
    m = session.manifest
    r, t = m.receipt, m.timing
    row = dict(
        session_id=sid,
        manifest_sha256=session.manifest_sha256,
        finalized_utc_ns=m.finalized_utc_ns,
        radio_id=r.radio_id,
        receiver_ids=list(r.plan.geometry.receiver_ids),
        sample_rate_hz=r.plan.geometry.sample_rate_hz,
        bandwidth_hz=r.plan.geometry.bandwidth_hz,
        visits=r.complete_visit_count,
        compressed_bytes=m.compressed_bytes,
        total_sample_count=m.total_sample_count,
        valid_sample_count=r.valid_sample_count,
        valid_duty_ppm=r.valid_duty_ppm,
        transition_invalid_sample_count=r.transition_invalid_sample_count,
        uncompressed_bytes=m.uncompressed_bytes,
        uncompressed_sha256=m.uncompressed_sha256,
        chunk_inventory_sha256=digest(canonical([c.model_dump(mode="json") for c in m.chunks])),
    )
    checks = {
        "not_finalized_at_cutoff": m.finalized_utc_ns > cutoff,
        "capture_incomplete": r.terminal.state != "completed" or r.terminal.error_code != 0,
        "source_span_unattested": not r.source_span_attested,
        "missing_samples": any(
            (
                r.transport_missing_sample_count,
                r.unreceived_tail_sample_count,
                r.unclassified_sample_count,
                r.terminal.device_dropped_events,
            )
        ),
        "incomplete_visits": r.complete_visit_count != len(r.events)
        or len(r.retained_visit_indices) != len(r.events),
        "restoration_incomplete": r.restoration.status != "restored",
        "empty": not m.chunks or not m.total_sample_count,
        "invalid_time": not t
        or not t.qualified
        or t.first_sample_earliest_utc_ns <= lower
        or t.terminal_realtime_ns > cutoff,
    }
    row["exclusion_reasons"] = [key for key, failed in checks.items() if failed]
    if t:
        row.update(
            capture_start_utc_ns=t.first_sample_estimate_utc_ns,
            capture_start_earliest_utc_ns=t.first_sample_earliest_utc_ns,
            capture_end_utc_ns=t.terminal_realtime_ns,
            utc_qualified=t.qualified,
        )
    row["pose_status"] = "not_collected"
    return row


def collect():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    if (ROOT / "manifest.json").exists():
        raise RuntimeError("DS10 already sealed; refusing to overwrite")
    ROOT.mkdir(exist_ok=True)
    for name in ("local", "pose", "analysis"):
        (ROOT / name).mkdir(exist_ok=True)
    snapshot_path = ROOT / "local/snapshot.json"
    parent = json.loads(PARENT.read_bytes())
    lower = max(r["capture_end_utc_ns"] for r in parent["captures"])
    store = AdaptiveHopIqStore(BULK, read_only=True)
    try:
        if not snapshot_path.exists():
            cutoff = 1790689728000000000  # 2026-09-29 13:48:48 UTC, request cutoff
            candidates = sorted(
                (r for r in store.tracking_metadata_index() if lower < r[1] <= cutoff),
                key=lambda r: (r[1], r[3]),
            )
            write(
                snapshot_path,
                dict(
                    cutoff=cutoff,
                    lower=lower,
                    candidates=candidates,
                    parent_manifest_sha256=digest(PARENT.read_bytes()),
                ),
            )
        snapshot = json.loads(snapshot_path.read_bytes())
        assert snapshot["parent_manifest_sha256"] == digest(PARENT.read_bytes())
        cutoff = snapshot["cutoff"]
        inventory_path = ROOT / "local/inventory.json"
        rows = json.loads(inventory_path.read_bytes()) if inventory_path.exists() else []
        done = {r["session_id"] for r in rows}
        start = time.monotonic()
        for _, _, _, sid in snapshot["candidates"]:
            if sid in done:
                continue
            if time.monotonic() - start > 40:
                break
            row = inspect(store, sid, lower, cutoff)
            evidence = {"observed_utc": utc(time.time_ns())}
            routes = {
                "glrt": f"/api/v2/scanner/adaptive-sessions/{sid}/analysis?probe_stride_ms=120",
                "tracking": f"/api/v1/scanner/tracking/{sid}",
            }
            for name, route in routes.items():
                with urlopen("http://127.0.0.1:8090" + route, timeout=20) as response:
                    evidence[name] = json.load(response)
            evidence["finished_utc"] = utc(time.time_ns())
            # Persist full API responses, including configurations and deferred groups.
            path = ROOT / "analysis" / (sid + ".json")
            write(path, evidence)
            row["analysis_evidence_sha256"] = digest(path.read_bytes())
            row["exclusion_reasons"].extend(
                analysis_reasons(row, evidence["glrt"], evidence["tracking"], cutoff)
            )
            rows.append(row)
            write(inventory_path, rows)
            print(
                f"Inspected {len(rows)}/{len(snapshot['candidates'])}: "
                f"{sid} {row['exclusion_reasons']}",
                flush=True,
            )
    finally:
        store.close()
    if len(rows) != len(snapshot["candidates"]):
        print("Checkpoint saved; rerun collect to continue", flush=True)
        return
    print("Inventory complete; run seal after reviewing counts", flush=True)


def totals(rows):
    return dict(
        recordings=len(rows),
        visits=sum(r["visits"] for r in rows),
        compressed_bytes=sum(r["compressed_bytes"] for r in rows),
        active_seconds_per_receiver=sum(
            r["valid_sample_count"] / r["sample_rate_hz"] for r in rows
        ),
        sample_rate_counts=dict(Counter(str(r["sample_rate_hz"]) for r in rows)),
    )


def seal():
    if (ROOT / "manifest.json").exists():
        raise RuntimeError("DS10 already sealed; refusing to overwrite")
    snapshot = json.loads((ROOT / "local/snapshot.json").read_bytes())
    rows = json.loads((ROOT / "local/inventory.json").read_bytes())
    assert [r["session_id"] for r in rows] == [r[3] for r in snapshot["candidates"]]
    admitted = [r for r in rows if not r["exclusion_reasons"]]
    assert admitted, "Refusing to mint an empty dataset"
    assert snapshot["parent_manifest_sha256"] == digest(PARENT.read_bytes())
    for row in rows:
        payload = (ROOT / "analysis" / (row["session_id"] + ".json")).read_bytes()
        assert digest(payload) == row["analysis_evidence_sha256"]
        evidence = json.loads(payload)
        reasons = analysis_reasons(row, evidence["glrt"], evidence["tracking"], snapshot["cutoff"])
        assert set(reasons).issubset(row["exclusion_reasons"])
    manifest = dict(
        schema="ds10-admission/v1",
        dataset_id="DS10",
        status="minted",
        inventory_cutoff_utc_ns=snapshot["cutoff"],
        inventory_cutoff_utc=utc(snapshot["cutoff"]),
        inventory_finished_utc=utc(time.time_ns()),
        parent_dataset="DS9",
        parent_manifest_sha256=snapshot["parent_manifest_sha256"],
        after_parent_capture_end_utc_ns=snapshot["lower"],
        storage_reader_release=str(Path("/opt/leo-tracker/current-api").resolve()),
        analysis_policy=(
            "Complete 120 ms-stride GLRT coverage and bound complete "
            "tracking/trajectory/TLE product created by cutoff; deferred "
            "candidate groups allowed and preserved. Readiness observed "
            "over inventory interval."
        ),
        integrity_scope=(
            "Read-only sealed metadata and chunk accounting; raw IQ not rehashed or copied."
        ),
        retention=dict(enforced_hold=False, payload_copied=False),
        counts=totals(admitted),
        captures=admitted,
        excluded=[r for r in rows if r["exclusion_reasons"]],
    )
    write(ROOT / "manifest.json", manifest)
    write(ROOT / "candidate-index.json", snapshot)
    ids = [r["session_id"] for r in admitted]
    write(
        ROOT / "evaluation-units.json",
        dict(
            schema="ds10-evaluation-units/v1",
            manifest_sha256=digest((ROOT / "manifest.json").read_bytes()),
            singles=[[sid] for sid in ids],
            groups_of_eight=[ids[i : i + 8] for i in range(0, len(ids) - 7, 8)],
            remainder=ids[len(ids) // 8 * 8 :],
            full=ids,
            rate_strata={
                rate: [r["session_id"] for r in admitted if str(r["sample_rate_hz"]) == rate]
                for rate in manifest["counts"]["sample_rate_counts"]
            },
            note=(
                "Chronological evaluation views, not train/test partitions; "
                "exclusions can create gaps."
            ),
        ),
    )
    paths = [
        ROOT / name
        for name in (
            "manifest.json",
            "candidate-index.json",
            "evaluation-units.json",
        )
    ]
    paths += [SOURCE / "mint.py", SOURCE / "test_mint.py"]
    paths += sorted((ROOT / "analysis").glob("*.json")) + sorted((ROOT / "pose").glob("*.json"))
    (ROOT / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {os.path.relpath(p, ROOT)}\n"
            for p in paths
        )
    )
    verify()


def verify():
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        assert digest((ROOT / relative).read_bytes()) == "sha256:" + expected, relative
    m = json.loads((ROOT / "manifest.json").read_bytes())
    parent = json.loads(PARENT.read_bytes())
    assert m["parent_manifest_sha256"] == digest(PARENT.read_bytes())
    assert m["after_parent_capture_end_utc_ns"] == max(
        r["capture_end_utc_ns"] for r in parent["captures"]
    )
    rows = m["captures"]
    assert totals(rows) == m["counts"]
    for key in ("session_id", "manifest_sha256"):
        assert len({r[key] for r in rows}) == len(rows)
        assert not {r[key] for r in rows} & {r[key] for r in parent["captures"]}
    snapshot = json.loads((ROOT / "candidate-index.json").read_bytes())
    assert {r[3] for r in snapshot["candidates"]} == {r["session_id"] for r in rows + m["excluded"]}
    for row in rows + m["excluded"]:
        payload = (ROOT / "analysis" / (row["session_id"] + ".json")).read_bytes()
        assert digest(payload) == row["analysis_evidence_sha256"]
        evidence = json.loads(payload)
        if row in rows:
            assert not row["exclusion_reasons"]
            assert not analysis_reasons(
                row, evidence["glrt"], evidence["tracking"], m["inventory_cutoff_utc_ns"]
            )
            assert row["capture_start_earliest_utc_ns"] > m["after_parent_capture_end_utc_ns"]
            assert (
                row["capture_end_utc_ns"] <= row["finalized_utc_ns"] <= m["inventory_cutoff_utc_ns"]
            )
        if row.get("pose_status") == "verified":
            payload = (ROOT / "pose" / (row["session_id"] + ".json")).read_bytes()
            assert digest(payload) == row["pose_file_sha256"]
            pose = json.loads(payload)
            assert (
                pose["session_id"] == row["session_id"]
                and pose["manifest_sha256"] == row["manifest_sha256"]
            )
    units = json.loads((ROOT / "evaluation-units.json").read_bytes())
    ids = [r["session_id"] for r in rows]
    assert units["manifest_sha256"] == digest((ROOT / "manifest.json").read_bytes())
    assert units["full"] == ids and units["singles"] == [[sid] for sid in ids]
    assert all(len(group) == 8 for group in units["groups_of_eight"])
    assert sum(units["groups_of_eight"], []) + units["remainder"] == ids
    print(json.dumps(dict(verified="DS10", **m["counts"], excluded=len(m["excluded"])), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("collect", "seal", "verify"))
    args = parser.parse_args()
    globals()[args.action]()
