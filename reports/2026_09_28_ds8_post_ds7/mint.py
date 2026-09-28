"""Freeze complete post-DS7 recordings at a fixed cutoff, using read-only metadata."""

import hashlib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

RELEASE = "17484895464c225ebba977487aa36d3d81658bd8"
CUTOFF = int(datetime(2026, 9, 28, 0, 22, 59, tzinfo=UTC).timestamp() * 1e9)


def digest(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    dest = Path(__file__).parent
    if (dest / "manifest.json").exists():
        raise RuntimeError("DS8 is already sealed; refusing to overwrite")
    work = dest / "local"
    work.mkdir(exist_ok=True)
    parent_path = dest.parent / "2026_09_27_ds7_post_ds6/manifest.json"
    parent = json.loads(parent_path.read_text())
    lower = max(c["capture_end_utc_ns"] for c in parent["captures"])
    prior_ids = {c["session_id"] for c in parent["captures"]}
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    index_path = work / "candidate-index.json"
    if not index_path.exists():
        rows = sorted(
            (
                r
                for r in store.tracking_metadata_index()
                if lower < r[1] <= CUTOFF and r[3] not in prior_ids
            ),
            key=lambda r: (r[1], r[3]),
        )
        index_path.write_text(json.dumps(rows))
    candidates = json.loads(index_path.read_text())
    progress_path = work / "inventory.json"
    rows = json.loads(progress_path.read_text()) if progress_path.exists() else []
    done = {r["session_id"] for r in rows}
    start = time.monotonic()
    for _, _, _, sid in candidates:
        if sid in done:
            continue
        if time.monotonic() - start > 80:
            break
        row = dict(session_id=sid, exclusion_reasons=[])
        try:
            session = store.inspect(sid)
            m, r, t = session.manifest, session.manifest.receipt, session.manifest.timing
            row.update(
                manifest_sha256=session.manifest_sha256,
                finalized_utc_ns=m.finalized_utc_ns,
                radio_id=r.radio_id,
                radio_serial=r.radio_serial,
                receiver_ids=list(r.plan.geometry.receiver_ids),
                sample_rate_hz=r.plan.geometry.sample_rate_hz,
                bandwidth_hz=r.plan.geometry.bandwidth_hz,
                visits=r.complete_visit_count,
                compressed_bytes=m.compressed_bytes,
                uncompressed_bytes=m.uncompressed_bytes,
                total_sample_count=m.total_sample_count,
                uncompressed_sha256=m.uncompressed_sha256,
                valid_sample_count=r.valid_sample_count,
                transition_invalid_sample_count=r.transition_invalid_sample_count,
                valid_duty_ppm=r.valid_duty_ppm,
                duty_target_met=r.duty_target_met,
                source_span_attested=r.source_span_attested,
                terminal_state=r.terminal.state,
                terminal_error_code=r.terminal.error_code,
                transport_missing_sample_count=r.transport_missing_sample_count,
                unreceived_tail_sample_count=r.unreceived_tail_sample_count,
                unclassified_sample_count=r.unclassified_sample_count,
                device_dropped_events=r.terminal.device_dropped_events,
                chunk_inventory_sha256=digest(
                    canonical([c.model_dump(mode="json") for c in m.chunks])
                ),
            )
            checks = dict(
                not_finalized_at_cutoff=m.finalized_utc_ns > CUTOFF,
                incomplete_terminal=r.terminal.state != "completed" or r.terminal.error_code != 0,
                source_span_unattested=not r.source_span_attested,
                missing_samples=any(
                    (
                        r.transport_missing_sample_count,
                        r.unreceived_tail_sample_count,
                        r.unclassified_sample_count,
                        r.terminal.device_dropped_events,
                    )
                ),
                incomplete_visits=r.complete_visit_count != len(r.events)
                or len(r.retained_visit_indices) != len(r.events),
                restoration_incomplete=r.restoration.status != "restored",
                empty=not m.chunks or not m.total_sample_count,
                invalid_time=not t
                or not t.qualified
                or t.first_sample_earliest_utc_ns <= lower
                or t.terminal_realtime_ns > CUTOFF,
            )
            row["exclusion_reasons"] = [k for k, v in checks.items() if v]
            if t:
                row.update(
                    capture_start_utc_ns=t.first_sample_estimate_utc_ns,
                    capture_start_earliest_utc_ns=t.first_sample_earliest_utc_ns,
                    capture_start_latest_utc_ns=t.first_sample_latest_utc_ns,
                    capture_end_utc_ns=t.terminal_realtime_ns,
                    utc_qualified=t.qualified,
                )
            pose = Path("/srv/bulk/leo/capture-pose/gauss-r20-roof-20260926-v1") / (sid + ".json")
            try:
                payload = pose.read_bytes()
                p = json.loads(payload)
                assert p["manifest_sha256"] == session.manifest_sha256 and p["session_id"] == sid
                assert p["binding_digest"] == digest(
                    canonical({k: v for k, v in p.items() if k != "binding_digest"})
                )
                assert p["pose_authority_digest"] == digest(canonical(p["pose_authority"]))
                assert p["capture_start_earliest_utc_ns"] == t.first_sample_earliest_utc_ns
                assert p["capture_end_utc_ns"] == t.terminal_realtime_ns
                assert (
                    p["pose_authority"]["valid_from_utc_ns"]
                    <= t.first_sample_earliest_utc_ns
                    < t.terminal_realtime_ns
                    < p["pose_authority"]["valid_until_utc_ns"]
                )
                (dest / "pose").mkdir(exist_ok=True)
                (dest / "pose" / (sid + ".json")).write_bytes(payload)
                row.update(
                    pose_status="verified",
                    pose_file_sha256=digest(payload),
                    pose_authority_revision=p["pose_authority"]["revision"],
                )
            except Exception as error:
                row.update(pose_status="unavailable_or_invalid", pose_error=str(error))
        except Exception as error:
            row["exclusion_reasons"].append("inspection_failed")
            row["inspection_error"] = str(error)
        rows.append(row)
        progress_path.write_text(json.dumps(rows, indent=2) + "\n")
        if len(rows) % 10 == 0:
            print(f"Inspected {len(rows)}/{len(candidates)}", flush=True)
    store.close()
    if len(rows) != len(candidates):
        print(f"Checkpoint {len(rows)}/{len(candidates)}; rerun to continue", flush=True)
        return
    admitted = [r for r in rows if not r["exclusion_reasons"]]
    result = dict(
        schema="ds8-admission/v1",
        dataset_id="DS8",
        status="minted",
        inventory_cutoff_utc_ns=CUTOFF,
        inventory_cutoff_utc="2026-09-28T00:22:59Z",
        parent_dataset="DS7",
        parent_manifest_sha256=digest(parent_path.read_bytes()),
        after_parent_capture_end_utc_ns=lower,
        source_bulk_root="/srv/bulk/leo",
        storage_reader_release=RELEASE,
        minted_utc=datetime.now(UTC).isoformat(),
        scope=(
            "Complete published recordings strictly after DS7 and finalized by fixed cutoff; "
            "no analysis-readiness filter"
        ),
        integrity_scope=(
            "Read-only sealed-manifest and chunk-accounting verification; payload IQ not rehashed"
        ),
        retention=dict(enforced_hold=False, payload_copied=False),
        counts=dict(
            recordings=len(admitted),
            visits=sum(r["visits"] for r in admitted),
            compressed_bytes=sum(r["compressed_bytes"] for r in admitted),
            sample_rate_counts=dict(Counter(r["sample_rate_hz"] for r in admitted)),
        ),
        captures=admitted,
        excluded=[r for r in rows if r["exclusion_reasons"]],
    )
    (dest / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    files = [dest / "manifest.json", *sorted((dest / "pose").glob("*.json"))]
    (dest / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(dest)}\n" for p in files
        )
    )
    print(json.dumps(result["counts"]), flush=True)


if __name__ == "__main__":
    main()
