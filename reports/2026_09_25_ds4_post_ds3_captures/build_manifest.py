#!/usr/bin/env python3
"""Build the read-only DS4 post-DS3 capture and evaluation-unit manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
POLICY = HERE / "freeze-policy.json"
DS3 = ROOT / "reports/2026_09_24_ds3_all_captures/manifest.json"


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def object_digest(value: Any) -> str:
    return sha256_bytes(canonical(value).encode())


def published_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verify_seal(path: Path) -> str:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    candidates = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    if not any(
        item.is_file() and item.read_text().strip().split()[0].removeprefix("sha256:") == actual
        for item in candidates
    ):
        raise ValueError(f"unsealed input: {path}")
    return "sha256:" + actual


def parse_utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"timezone missing: {value}")
    return result.astimezone(UTC)


def iso_ns(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")


def _dwell_ms(events: Any, sample_rate_hz: Any) -> list[float]:
    if not isinstance(events, list) or not isinstance(sample_rate_hz, int) or sample_rate_hz <= 0:
        return []
    return sorted(
        {
            round(
                1000
                * (event["valid_end_counter_exclusive"] - event["valid_start_counter"])
                / sample_rate_hz,
                6,
            )
            for event in events
            if isinstance(event, dict)
            and isinstance(event.get("valid_end_counter_exclusive"), int)
            and isinstance(event.get("valid_start_counter"), int)
        }
    )


def discover(raw_root: Path, lower: datetime, upper: datetime) -> list[dict[str, Any]]:
    """Read capture manifests without changing the recording tree."""
    rows: list[dict[str, Any]] = []
    for path in sorted(raw_root.glob("scan-fw-*/manifest.json")):
        payload = path.read_bytes()
        envelope = json.loads(payload)
        raw = envelope.get("manifest") if isinstance(envelope, dict) else None
        if not isinstance(raw, dict):
            continue
        timing = raw.get("timing")
        receipt = raw.get("receipt")
        if not isinstance(timing, dict) or not isinstance(receipt, dict):
            continue
        start_ns = timing.get("first_sample_estimate_utc_ns")
        if not isinstance(start_ns, int):
            continue
        started = datetime.fromtimestamp(start_ns / 1_000_000_000, UTC)
        if not lower < started <= upper:
            continue
        terminal = receipt.get("terminal") if isinstance(receipt.get("terminal"), dict) else {}
        qualified = timing.get("qualified") is True
        complete = terminal.get("state") == "completed"
        finalized_ns = raw.get("finalized_utc_ns")
        finalized = (
            datetime.fromtimestamp(finalized_ns / 1_000_000_000, UTC)
            if isinstance(finalized_ns, int)
            else None
        )
        finalized_by_cutoff = finalized is not None and finalized <= upper
        admitted = qualified and complete and finalized_by_cutoff
        session_id = raw.get("session_id")
        if not isinstance(session_id, str) or not session_id.startswith("scan-fw-"):
            raise ValueError(f"invalid session id in {path}")
        rows.append(
            {
                "session_id": session_id,
                "capture_start_utc": iso_ns(start_ns),
                "finalized_utc": iso_ns(finalized_ns) if isinstance(finalized_ns, int) else None,
                "recording_manifest_path": str(path),
                "recording_manifest_file_sha256": sha256_bytes(payload),
                "recording_manifest_content_sha256": envelope.get("sha256"),
                "capture_schema_version": raw.get("schema_version"),
                "receipt_schema_version": receipt.get("schema_version"),
                "timing_schema_version": timing.get("schema_version"),
                "radio_id": receipt.get("radio_id"),
                "sample_rate_hz": timing.get("sample_rate_hz"),
                "sample_format": raw.get("sample_format"),
                "sample_layout": raw.get("sample_layout"),
                "total_sample_count": raw.get("total_sample_count"),
                "complete_visit_count": receipt.get("complete_visit_count"),
                "dwell_ms_observed": _dwell_ms(receipt.get("events"), timing.get("sample_rate_hz")),
                "valid_duty_ppm": receipt.get("valid_duty_ppm"),
                "recording_complete": complete,
                "qualified_utc_timing": qualified,
                "source_span_attested": receipt.get("source_span_attested") is True,
                "device_dropped_events": terminal.get("device_dropped_events"),
                "admission_status": "included" if admitted else "excluded",
                "exclusion_reason": None if admitted else (
                    "capture_finalized_after_audit_cutoff"
                    if qualified and complete and finalized is not None and finalized > upper
                    else "capture_not_qualified_completed_and_finalized_by_audit_cutoff"
                ),
            }
        )
    rows.sort(key=lambda row: (row["capture_start_utc"], row["session_id"]))
    if len({row["session_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate DS4 session id")
    return rows


def _unit(unit_id: str, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [row["session_id"] for row in sessions]
    return {
        "unit_id": unit_id,
        "session_count": len(ids),
        "session_ids": ids,
        "capture_start_utc": sessions[0]["capture_start_utc"],
        "capture_end_start_utc": sessions[-1]["capture_start_utc"],
        "session_inventory_sha256": object_digest(ids),
    }


def assemble(
    policy: dict[str, Any], ds3: dict[str, Any], rows: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if policy.get("schema") != "ds4-freeze-policy/v1":
        raise ValueError("unexpected DS4 policy schema")
    ds3_captures = [
        row for row in ds3.get("captures", []) if row.get("admission_status") == "included"
    ]
    if not ds3_captures:
        raise ValueError("DS3 has no admitted captures")
    ds3_last = max(str(row["capture_start_utc"]) for row in ds3_captures)
    lower_text = str(policy["capture_start_lower_bound_utc"])
    if parse_utc(ds3_last) != parse_utc(lower_text):
        raise ValueError("DS4 lower bound is not DS3's last admitted recording")
    admitted = [row for row in rows if row["admission_status"] == "included"]
    if not admitted:
        raise ValueError("DS4 contains no admitted sessions")
    ds3_ids = {str(row["session_id"]) for row in ds3_captures}
    overlap = ds3_ids & {row["session_id"] for row in admitted}
    if overlap:
        raise ValueError(f"DS3/DS4 overlap: {sorted(overlap)}")

    ids = [row["session_id"] for row in admitted]
    group_count = len(ids) // 8
    grouped_count = group_count * 8
    singles = [_unit(f"ds4-single-{index:03d}", [row]) for index, row in enumerate(admitted, 1)]
    groups = [
        _unit(f"ds4-group8-{index + 1:03d}", admitted[index * 8 : (index + 1) * 8])
        for index in range(group_count)
    ]
    full = _unit("ds4-full", admitted)
    inventory_digest = object_digest(ids)
    manifest = {
        "schema": "ds4-post-ds3-admission/v1",
        "dataset_name": "DS4",
        "audit_observed_utc": policy["audit_observed_utc"],
        "capture_start_interval": {
            "lower_utc": lower_text,
            "lower_inclusive": False,
            "upper_utc": policy["capture_start_upper_bound_utc"],
            "upper_inclusive": True,
        },
        "source_root": policy["source_root"],
        "reference_coordinate_present": False,
        "ds3_boundary": {
            "last_admitted_capture_start_utc": ds3_last,
            "overlap_session_count": 0,
        },
        "counts": {
            "discovered_in_interval": len(rows),
            "admitted": len(admitted),
            "excluded": len(rows) - len(admitted),
            "single_scan_units": len(singles),
            "complete_8_scan_units": len(groups),
            "sessions_in_complete_8_scan_units": grouped_count,
            "8_scan_remainder_sessions": len(admitted) - grouped_count,
            "full_dataset_units": 1,
        },
        "session_inventory_sha256": inventory_digest,
        "captures": rows,
        "exclusions": [row for row in rows if row["admission_status"] == "excluded"],
        "grouping_contract": {
            "order": "ascending (capture_start_utc, session_id)",
            "single_scans": "one admitted whole session per unit",
            "groups_of_8": "non-overlapping consecutive chunks of exactly eight admitted sessions",
            "remainder_policy": "record separately; never label a partial chunk as an 8-scan unit",
            "full_dataset": "one unit containing every admitted session",
            "receiver_leakage_policy": (
                "all receivers, visits and tracks from a session remain in its unit"
            ),
        },
    }
    units = {
        "schema": "ds4-evaluation-units/v1",
        "dataset_name": "DS4",
        "reference_coordinate_present": False,
        "session_inventory_sha256": inventory_digest,
        "single_scans": singles,
        "groups_of_8": groups,
        "groups_of_8_remainder": {
            "session_count": len(admitted) - grouped_count,
            "session_ids": ids[grouped_count:],
            "eligible_as_8_scan_unit": False,
        },
        "full_dataset": full,
    }
    return manifest, units


def write_sealed(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        pending = Path(handle.name)
    pending.replace(path)
    digest = hashlib.sha256(text.encode()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n")
    return "sha256:" + digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY)
    parser.add_argument("--ds3", type=Path, default=DS3)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument(
        "--manifest-logical-path",
        type=Path,
        help="stable published path to bind when output-dir is a staging directory",
    )
    args = parser.parse_args()
    policy = load(args.policy)
    ds3 = load(args.ds3)
    verify_seal(args.policy)
    ds3_sha256 = verify_seal(args.ds3)
    raw_root = args.raw_root or Path(str(policy["source_root"]))
    rows = discover(
        raw_root,
        parse_utc(str(policy["capture_start_lower_bound_utc"])),
        parse_utc(str(policy["capture_start_upper_bound_utc"])),
    )
    manifest, units = assemble(policy, ds3, rows)
    manifest["inputs"] = {
        "freeze_policy": {
            "path": published_path(args.policy),
            "sha256": verify_seal(args.policy),
        },
        "ds3_manifest": {"path": published_path(args.ds3), "sha256": ds3_sha256},
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_sha256 = write_sealed(manifest_path, manifest)
    logical_manifest = args.manifest_logical_path or manifest_path
    units["admission_manifest"] = {
        "path": published_path(logical_manifest),
        "sha256": manifest_sha256,
    }
    write_sealed(args.output_dir / "evaluation-units.json", units)
    print(canonical(manifest["counts"]), end="")


if __name__ == "__main__":
    main()
