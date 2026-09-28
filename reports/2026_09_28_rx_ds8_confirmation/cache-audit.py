"""Read-only audit of the sealed DS8 cache and grouped partition metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def resources(path: Path) -> dict[str, Any]:
    text = path.read_text()
    elapsed = re.search(r"Elapsed .*?: ([^\n]+)", text)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    status = re.search(r"Exit status: (\d+)", text)
    assert elapsed and rss and status
    return {
        "elapsed_wall": elapsed.group(1),
        "max_rss_kib": int(rss.group(1)),
        "exit_status": int(status.group(1)),
    }


def audit(args: argparse.Namespace) -> dict[str, Any]:
    readiness = json.loads(args.readiness.read_text())
    inventory = json.loads(args.inventory.read_text())
    manifest = json.loads(args.manifest.read_text())
    partitions = json.loads(args.partitions.read_text())
    ready = {row["session_id"]: row for row in readiness["selected"]}
    inv = {row["session_id"]: row for row in inventory}
    sessions = {row["pose"]["session_id"]: row for row in manifest["sessions"]}
    expected = set(ready)
    assert len(expected) == 4 and set(inv) == set(sessions) == expected
    assert sorted(row["sample_rate_hz"] for row in ready.values()) == [
        2_500_000,
        5_000_000,
        7_500_000,
        10_000_000,
    ]
    assert manifest["readiness_sha256"] == sha256(args.readiness)
    assert manifest["ds8_manifest_sha256"] == "sha256:" + readiness["source_sha256"]["ds8_manifest"]
    assert manifest["candidate_or_outcome_fields_inspected"] is False

    cache_rows = []
    for sid in sorted(expected):
        source, row, receipt = ready[sid], inv[sid], sessions[sid]
        path = Path(row["cache_file"])
        assert row["ready"] is True and row["split"] == receipt["split"] == "evaluation"
        for key in ("sample_rate_hz", "input_manifest_sha256", "analysis_manifest_sha256"):
            assert row[key] == source[key]
        assert receipt["analysis_manifest_sha256"] == source["analysis_manifest_sha256"]
        assert sha256(path) == row["cache_sha256"] == receipt["cache_sha256"]
        obj = pickle.loads(path.read_bytes())
        assert type(obj).__module__ == "leo.contracts.scanner_tracking"
        assert type(obj).__name__ == "TrackingInput"
        for key in (
            "session_id",
            "sample_rate_hz",
            "input_manifest_sha256",
            "analysis_manifest_sha256",
        ):
            assert getattr(obj, key) == row.get(key, sid if key == "session_id" else None)
        assert obj.qualified is True and len(obj.probes) == source["probes"]
        assert obj.capture_start_utc_ns == source["capture_start_utc_ns"]
        assert obj.capture_start_utc_ns >= source["capture_start_utc_ns"]
        assert obj.capture_end_utc_ns <= source["capture_end_utc_ns"]
        pose = receipt["pose"]
        assert pose["binding_digest"] == source["pose_binding_digest"]
        assert pose["pose_authority"]["revision"] == source["pose_revision"]
        assert pose["manifest_sha256"] == source["input_manifest_sha256"]
        assert pose["pose_authority_digest"] == canonical_sha(pose["pose_authority"])
        assert pose["pose_authority"]["valid_from_utc_ns"] <= obj.capture_start_utc_ns
        assert obj.capture_end_utc_ns <= pose["pose_authority"]["valid_until_utc_ns"]
        identities: set[tuple[int, int, int]] = set()
        pairs: dict[tuple[int, int], list[Any]] = defaultdict(list)
        for probe in obj.probes:
            ident = (probe.visit_index, probe.probe_index, probe.receiver_id)
            assert ident not in identities
            identities.add(ident)
            pairs[(probe.visit_index, probe.probe_index)].append(probe)
        assert all(len(value) == 2 for value in pairs.values())
        visits: dict[int, list[Any]] = defaultdict(list)
        for probe in obj.probes:
            visits[probe.visit_index].append(probe)
        assert all(len(value) == 2 for value in visits.values())
        for value in pairs.values():
            a, b = sorted(value, key=lambda p: p.receiver_id)
            assert (a.receiver_id, b.receiver_id) == (0, 1)
            assert (a.probe_start_ms, a.channel, a.edge, a.valid_start_counter, a.actual_rf_hz) == (
                b.probe_start_ms,
                b.channel,
                b.edge,
                b.valid_start_counter,
                b.actual_rf_hz,
            )
        assert len(pairs) * 2 == len(obj.probes)
        cache_rows.append(
            {
                "session_id": sid,
                "sample_rate_hz": obj.sample_rate_hz,
                "probes": len(obj.probes),
                "paired_probe_keys": len(pairs),
                "complete_visits": len(visits),
                "tracking_capture_start_utc_ns": obj.capture_start_utc_ns,
                "tracking_capture_end_utc_ns": obj.capture_end_utc_ns,
                "source_capture_end_utc_ns": source["capture_end_utc_ns"],
                "cache_sha256": sha256(path),
                "pose_binding_digest": pose["binding_digest"],
            }
        )

    windows = partitions["windows"]
    groups = {g["group_id"]: g for g in partitions["groups"]}
    assert (
        len(windows)
        == len({w["source_window_id"] for w in windows})
        == partitions["counts"]["windows"]
    )
    assert set(w["session_id"] for w in windows) == expected
    role_by_id = {w["source_window_id"]: w["role"] for w in windows}
    for w in windows:
        g = groups[w["group_id"]]
        assert g["role"] == w["role"] and g["session_id"] == w["session_id"]
    assert all(len({role_by_id[x] for x in g["window_ids"]}) == 1 for g in groups.values())
    time_rows: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for window in windows:
        time_rows[window["session_id"]].append(
            (window["window_start_utc_ns"], window["window_end_utc_ns"], window["role"])
        )
    cross_role_time = 0
    for rows in time_rows.values():
        active: list[tuple[int, str]] = []
        for start, end, role in sorted(rows):
            active = [item for item in active if item[0] > start]
            cross_role_time += sum(other_role != role for _, other_role in active)
            active.append((end, role))
    assert cross_role_time == 0

    # Read only identities and source support metadata from opportunities.
    opportunities: dict[str, dict[str, Any]] = {}
    supports: list[tuple[str, str, int, int, str, str]] = []
    with args.opportunities.open() as handle:
        for line in handle:
            row = json.loads(line)
            wid = row["source_window_id"]
            assert wid not in opportunities
            opportunities[wid] = row
            for view in row["receivers"].values():
                for candidate in view["candidates"]:
                    support = candidate.get("source_interval")
                    if support is not None:
                        supports.append(
                            (
                                row["source_window"]["session_id"],
                                str(support.get("stream_id")),
                                int(support["source_sample_start"]),
                                int(support["source_sample_end"]),
                                wid,
                                role_by_id[wid],
                            )
                        )
    assert set(opportunities) == set(role_by_id)
    cross_role = 0
    by_stream: dict[tuple[str, str], list[tuple[int, int, str, str]]] = defaultdict(list)
    for sid, stream, start, end, wid, role in supports:
        by_stream[(sid, stream)].append((start, end, wid, role))
    for rows in by_stream.values():
        active: list[tuple[int, str, str]] = []
        for start, end, wid, role in sorted(rows):
            active = [x for x in active if x[0] > start]
            cross_role += sum(
                other_role != role and other_wid != wid for _, other_wid, other_role in active
            )
            active.append((end, wid, role))
    assert cross_role == 0
    computed_roles = Counter(w["role"] for w in windows)
    assert dict(computed_roles) == partitions["counts"]["windows_by_role"]
    assert partitions["overlap_validation"]["connected_groups_cross_roles"] == 0

    return {
        "schema": "rx-ds8-confirmation-cache-audit/v1",
        "status": "passed",
        "scope": (
            "Public cache metadata, sealed provenance, and partition source-support "
            "metadata only; candidate measurements and outcomes were not inspected."
        ),
        "source_sha256": {
            name: sha256(getattr(args, name))
            for name in ("readiness", "inventory", "manifest", "partitions", "opportunities")
        },
        "fixed_sessions": sorted(expected),
        "cache": cache_rows,
        "partition_audit": {
            "windows": len(windows),
            "groups": len(groups),
            "roles": dict(sorted(computed_roles.items())),
            "source_support_rows": len(supports),
            "cross_role_source_support_overlaps": cross_role,
            "cross_role_window_time_overlaps": cross_role_time,
            "all_groups_single_role": True,
            "all_opportunities_accounted": True,
        },
        "resources": {
            "cache_packaging": resources(args.cache_resources),
            "model_fit": resources(args.model_resources),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in (
        "readiness",
        "inventory",
        "manifest",
        "partitions",
        "opportunities",
        "cache_resources",
        "model_resources",
        "output",
    ):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    result = audit(args)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
