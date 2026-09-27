#!/usr/bin/env python3
"""Build sealed, truth-blind DS5 admission and evaluation-unit manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
POLICY = HERE / "freeze-policy.json"


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


def _active_dwell_metrics(events: Any, sample_rate_hz: Any, valid_duty_ppm: Any) -> dict[str, Any]:
    """Return exposure metrics from attested valid spans, without using position truth."""
    if not isinstance(events, list) or not isinstance(sample_rate_hz, int) or sample_rate_hz <= 0:
        return {
            "active_dwell_seconds": None,
            "median_visit_dwell_ms": None,
            "valid_duty_fraction": None,
        }
    durations = [
        (event["valid_end_counter_exclusive"] - event["valid_start_counter"]) / sample_rate_hz
        for event in events
        if isinstance(event, dict)
        and isinstance(event.get("valid_end_counter_exclusive"), int)
        and isinstance(event.get("valid_start_counter"), int)
        and event["valid_end_counter_exclusive"] >= event["valid_start_counter"]
    ]
    return {
        "active_dwell_seconds": round(sum(durations), 9),
        "median_visit_dwell_ms": round(1000 * median(durations), 6) if durations else None,
        "valid_duty_fraction": (
            round(valid_duty_ppm / 1_000_000, 9)
            if isinstance(valid_duty_ppm, int) and 0 <= valid_duty_ppm <= 1_000_000
            else None
        ),
    }


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
        if not lower <= started <= upper:
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
        events = receipt.get("events")
        sample_rate_hz = timing.get("sample_rate_hz")
        valid_duty_ppm = receipt.get("valid_duty_ppm")
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
                "sample_rate_hz": sample_rate_hz,
                "sample_format": raw.get("sample_format"),
                "sample_layout": raw.get("sample_layout"),
                "total_sample_count": raw.get("total_sample_count"),
                "complete_visit_count": receipt.get("complete_visit_count"),
                "dwell_ms_observed": _dwell_ms(events, sample_rate_hz),
                "valid_duty_ppm": valid_duty_ppm,
                **_active_dwell_metrics(events, sample_rate_hz, valid_duty_ppm),
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
        raise ValueError("duplicate DS5 session id")
    return rows


def _rate_composition(sessions: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(int(row["sample_rate_hz"]) for row in sessions)
    return {str(rate): counts[rate] for rate in sorted(counts)}


def _unit(unit_id: str, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [row["session_id"] for row in sessions]
    active = [float(row["active_dwell_seconds"]) for row in sessions]
    duty = [float(row["valid_duty_fraction"]) for row in sessions]
    visit_ms = [float(row["median_visit_dwell_ms"]) for row in sessions]
    return {
        "unit_id": unit_id,
        "session_count": len(ids),
        "session_ids": ids,
        "capture_start_utc": sessions[0]["capture_start_utc"],
        "capture_end_start_utc": sessions[-1]["capture_start_utc"],
        "sample_rate_composition": _rate_composition(sessions),
        "active_dwell_support": {
            "total_seconds": round(sum(active), 9),
            "minimum_session_seconds": min(active),
            "median_session_seconds": median(active),
            "maximum_session_seconds": max(active),
            "median_valid_duty_fraction": median(duty),
            "median_visit_dwell_ms": median(visit_ms),
        },
        "session_inventory_sha256": object_digest(ids),
    }


def _active_time_strata(sessions: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    """Create deterministic rank-balanced terciles from measured active exposure."""
    ranked = sorted(
        sessions,
        key=lambda row: (float(row["active_dwell_seconds"]), str(row["session_id"])),
    )
    names = ("low", "middle", "high")
    membership: dict[str, str] = {}
    strata: dict[str, Any] = {}
    total = len(ranked)
    for index, name in enumerate(names):
        start = index * total // 3
        stop = (index + 1) * total // 3
        subset = ranked[start:stop]
        for row in subset:
            membership[str(row["session_id"])] = name
        strata[name] = {
            "definition": "rank-balanced tercile of measured active_dwell_seconds; ties by session_id",
            "session_count": len(subset),
            "minimum_active_dwell_seconds": float(subset[0]["active_dwell_seconds"]),
            "maximum_active_dwell_seconds": float(subset[-1]["active_dwell_seconds"]),
            "ordered_session_ids": [str(row["session_id"]) for row in subset],
            "subset_unit": _unit(f"ds5-active-{name}-full", subset),
        }
    return strata, membership


def assemble(
    policy: dict[str, Any], rows: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if policy.get("schema") != "ds5-freeze-policy/v1":
        raise ValueError("unexpected DS5 policy schema")
    if policy.get("reference_coordinate_present") is not False:
        raise ValueError("DS5 policy must be truth-blind")
    admitted = [row for row in rows if row["admission_status"] == "included"]
    if not admitted:
        raise ValueError("DS5 contains no admitted sessions")
    if any(not isinstance(row.get("sample_rate_hz"), int) for row in admitted):
        raise ValueError("admitted DS5 capture has no integer sample rate")
    if any(
        not isinstance(row.get(field), (int, float))
        for row in admitted
        for field in ("active_dwell_seconds", "valid_duty_fraction", "median_visit_dwell_ms")
    ):
        raise ValueError("admitted DS5 capture lacks measured active-dwell metadata")

    active_strata, active_membership = _active_time_strata(admitted)
    for row in admitted:
        row["active_dwell_time_stratum"] = active_membership[str(row["session_id"])]

    ids = [row["session_id"] for row in admitted]
    group_count = len(ids) // 8
    grouped_count = group_count * 8
    singles = [_unit(f"ds5-single-{index:03d}", [row]) for index, row in enumerate(admitted, 1)]
    groups = [
        _unit(f"ds5-group8-{index + 1:03d}", admitted[index * 8 : (index + 1) * 8])
        for index in range(group_count)
    ]
    full = _unit("ds5-full", admitted)
    rates = sorted({int(row["sample_rate_hz"]) for row in admitted})
    rate_strata = {
        str(rate): {
            "sample_rate_hz": rate,
            "session_count": len(subset := [row for row in admitted if row["sample_rate_hz"] == rate]),
            "ordered_single_session_ids": [row["session_id"] for row in subset],
            "subset_unit": _unit(f"ds5-rate-{rate}-full", subset),
        }
        for rate in rates
    }
    rate_active_cross_strata = {
        str(rate): {
            name: {
                "session_count": len(
                    subset := [
                        row
                        for row in admitted
                        if row["sample_rate_hz"] == rate
                        and row["active_dwell_time_stratum"] == name
                    ]
                ),
                "ordered_session_ids": [row["session_id"] for row in subset],
            }
            for name in ("low", "middle", "high")
        }
        for rate in rates
    }
    inventory_digest = object_digest(ids)
    manifest = {
        "schema": "ds5-admission/v1",
        "dataset_name": "DS5",
        "audit_observed_utc": policy["audit_observed_utc"],
        "capture_start_interval": {
            "lower_utc": policy["capture_start_lower_bound_utc"],
            "lower_inclusive": True,
            "upper_utc": policy["capture_start_upper_bound_utc"],
            "upper_inclusive": True,
            "window_basis": policy["window_basis"],
        },
        "source_root": policy["source_root"],
        "reference_coordinate_present": False,
        "counts": {
            "discovered_in_interval": len(rows),
            "admitted": len(admitted),
            "excluded": len(rows) - len(admitted),
            "single_scan_units": len(singles),
            "complete_8_scan_units": len(groups),
            "sessions_in_complete_8_scan_units": grouped_count,
            "8_scan_remainder_sessions": len(admitted) - grouped_count,
            "sample_rate_strata": len(rate_strata),
            "active_dwell_time_strata": len(active_strata),
            "full_dataset_units": 1,
        },
        "session_inventory_sha256": inventory_digest,
        "captures": rows,
        "exclusions": [row for row in rows if row["admission_status"] == "excluded"],
        "grouping_contract": {
            "order": "ascending (capture_start_utc, session_id)",
            "single_scans": "one admitted whole session per unit",
            "groups_of_8": "non-overlapping consecutive chunks of exactly eight admitted sessions",
            "groups_of_8_rate_policy": "chronology is preserved; groups are not rearranged by sample rate",
            "remainder_policy": "record separately; never label a partial chunk as an 8-scan unit",
            "rate_strata": "ordered membership and a complete subset unit for each recorded sample_rate_hz",
            "active_dwell_time_strata": (
                "rank-balanced low/middle/high terciles of measured valid-span exposure; "
                "ties break by session_id; no position truth is used"
            ),
            "full_dataset": "one unit containing every admitted session",
            "receiver_leakage_policy": "all receivers, visits and tracks from a session remain in its unit",
        },
    }
    units = {
        "schema": "ds5-evaluation-units/v1",
        "dataset_name": "DS5",
        "reference_coordinate_present": False,
        "session_inventory_sha256": inventory_digest,
        "single_scans": singles,
        "sample_rate_strata": rate_strata,
        "active_dwell_time_strata": active_strata,
        "sample_rate_active_dwell_cross_strata": rate_active_cross_strata,
        "groups_of_8": groups,
        "groups_of_8_remainder": {
            "session_count": len(admitted) - grouped_count,
            "session_ids": ids[grouped_count:],
            "sample_rate_composition": _rate_composition(admitted[grouped_count:]),
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
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--manifest-logical-path", type=Path)
    args = parser.parse_args()
    policy = load(args.policy)
    policy_sha256 = verify_seal(args.policy)
    raw_root = args.raw_root or Path(str(policy["source_root"]))
    rows = discover(
        raw_root,
        parse_utc(str(policy["capture_start_lower_bound_utc"])),
        parse_utc(str(policy["capture_start_upper_bound_utc"])),
    )
    manifest, units = assemble(policy, rows)
    manifest["inputs"] = {
        "freeze_policy": {"path": published_path(args.policy), "sha256": policy_sha256}
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
