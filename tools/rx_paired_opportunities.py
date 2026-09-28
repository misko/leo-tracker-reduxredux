"""Export hash-verified, opportunity-complete dual-RX candidate observations.

Run in the production interpreter that owns the public TrackingInput pickle
contract.  This tool does no association or fitting; satellite IDs are null.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _get(value: Any, name: str, default: Any = None) -> Any:
    return getattr(value, name, default)


def _id(prefix: str, value: dict[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"{prefix}:sha256:{hashlib.sha256(body.encode()).hexdigest()}"


def _time(raw: Any, probe: Any) -> dict[str, Any]:
    timing = _get(raw, "timing")
    first, base, counter, rate = (
        _get(timing, "first_sample_estimate_utc_ns"),
        _get(timing, "session_start_device_sample_counter"),
        _get(probe, "valid_start_counter"),
        _get(raw, "sample_rate_hz"),
    )
    offset, duration = _get(probe, "probe_start_ms"), _get(raw, "probe_ms")
    if None in (first, base, counter, rate, offset, duration) or not rate:
        return {
            "window_start_utc_ns": None,
            "window_end_utc_ns": None,
            "time_binding": "unavailable",
        }
    relative = counter - base + offset * rate // 1_000
    samples = duration * rate // 1_000
    return {
        "window_start_utc_ns": first + round(relative * 1e9 / rate),
        "window_end_utc_ns": first + round((relative + samples) * 1e9 / rate),
        "time_binding": "first_sample_estimate_utc_ns + counter/probe offset",
        "first_sample_estimate_utc_ns": first,
        "session_start_device_sample_counter": base,
        "valid_start_counter": counter,
        "probe_start_ms": offset,
        "probe_ms": duration,
    }


def projected_candidates(raw: Any) -> dict[tuple[int, int, int, int], Any]:
    from leo.application.scanner_trajectory import project_scanner_candidates

    result = {}
    for item in project_scanner_candidates(raw):
        key = (item.visit_index, item.probe_index, item.receiver_id, item.candidate_rank)
        if key in result:
            raise ValueError(f"duplicate projected candidate binding: {key}")
        result[key] = item
    return result


def _candidate(
    raw: Any,
    probe: Any,
    window_id: str,
    candidate: Any,
    projected: dict[tuple[int, int, int, int], Any],
) -> dict[str, Any]:
    fields = {
        name: _get(candidate, name)
        for name in (
            "candidate_rank",
            "integer_epoch_sample",
            "fractional_epoch_offset_samples",
            "fractional_tracking_cfo_hz",
            "fractional_exact_score",
            "fractional_control_score",
            "fractional_margin",
        )
    }
    fields["passed_fractional_margin_gate"] = bool(_get(candidate, "passed_fractional_margin_gate"))
    receiver = _get(probe, "receiver_id")
    anchor = ":".join(
        str(value)
        for value in (
            _get(raw, "session_id"),
            _get(probe, "visit_index"),
            _get(probe, "probe_index"),
            receiver,
            fields["candidate_rank"],
        )
    )
    point = projected.get(
        (_get(probe, "visit_index"), _get(probe, "probe_index"), receiver, fields["candidate_rank"])
    )
    return {
        "candidate_id": _id(
            "rx-candidate/v1", {"source_window_id": window_id, "receiver_id": receiver, **fields}
        ),
        "anchor_key": anchor,
        "projected_candidate_id": None if point is None else point.candidate_id,
        "source_interval": None
        if point is None
        else {
            name: _get(point, name)
            for name in (
                "source_group_id",
                "source_sample_start",
                "source_sample_end",
                "support_center_utc_ns",
                "stream_id",
            )
        },
        "satellite_id": None,
        "session_id": _get(raw, "session_id"),
        "visit_index": _get(probe, "visit_index"),
        "probe_index": _get(probe, "probe_index"),
        "receiver_id": receiver,
        "probe_start_ms": _get(probe, "probe_start_ms"),
        **fields,
    }


def _view(
    raw: Any, probe: Any | None, window_id: str, projected: dict[tuple[int, int, int, int], Any]
) -> dict[str, Any]:
    if probe is None:
        return {
            "receiver_status": "missing_receiver_probe",
            "candidate_count": 0,
            "passing_candidate_count": 0,
            "candidates": [],
        }
    candidates = [
        _candidate(raw, probe, window_id, item, projected) for item in _get(probe, "candidates", ())
    ]
    if not _get(raw, "qualified", False):
        status = "unqualified_input"
    elif not _get(_get(raw, "timing"), "qualified", False):
        status = "unqualified_timing"
    elif any(item["passed_fractional_margin_gate"] for item in candidates):
        status = "observed_candidate_present"
    else:
        status = "observed_candidate_absent"
    return {
        "receiver_status": status,
        "receiver_id": _get(probe, "receiver_id"),
        "actual_rf_hz": _get(probe, "actual_rf_hz"),
        "payload_start_sample": _get(probe, "payload_start_sample"),
        "candidate_count": len(candidates),
        "passing_candidate_count": sum(
            item["passed_fractional_margin_gate"] for item in candidates
        ),
        "candidates": candidates,
    }


def export_input(
    raw: Any,
    *,
    split: str,
    cache_sha256: str,
    projected: dict[tuple[int, int, int, int], Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Produce one JSONL-ready row per source window and receiver bindings."""
    projected = projected or {}
    grouped: dict[tuple[Any, Any, Any], dict[int, list[Any]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for probe in _get(raw, "probes", ()):
        grouped[
            (_get(probe, "visit_index"), _get(probe, "probe_index"), _get(probe, "probe_start_ms"))
        ][_get(probe, "receiver_id")].append(probe)
    rows: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for key in sorted(grouped):
        receivers = grouped[key]
        primary = next(values[0] for values in receivers.values() if values)
        source = {
            "session_id": _get(raw, "session_id"),
            "visit_index": key[0],
            "probe_index": key[1],
            "probe_start_ms": key[2],
            "channel": _get(primary, "channel"),
            "edge": _get(primary, "edge"),
            "valid_start_counter": _get(primary, "valid_start_counter"),
            "sample_rate_hz": _get(raw, "sample_rate_hz"),
        }
        window_id = _id("rx-source-window/v1", source)
        views: dict[str, Any] = {}
        for receiver in (0, 1):
            probes = receivers.get(receiver, [])
            if len(probes) > 1:
                views[f"rx{receiver}"] = {
                    "receiver_status": "duplicate_receiver_probe",
                    "candidate_count": 0,
                    "passing_candidate_count": 0,
                    "candidates": [],
                }
                continue
            probe = probes[0] if probes else None
            views[f"rx{receiver}"] = _view(raw, probe, window_id, projected)
            if probe is not None:
                bindings.append(
                    {
                        "schema": "rx-paired-source-binding/v1",
                        "source_window_id": window_id,
                        "receiver_id": receiver,
                        "cache_sha256": cache_sha256,
                        "source_window": source,
                        **_time(raw, probe),
                    }
                )
        states = {view["receiver_status"] for view in views.values()}
        pair_consistent = len(receivers.get(0, [])) == len(receivers.get(1, [])) == 1 and (
            tuple(
                _get(receivers[0][0], field)
                for field in ("channel", "edge", "valid_start_counter", "actual_rf_hz")
            )
            == tuple(
                _get(receivers[1][0], field)
                for field in ("channel", "edge", "valid_start_counter", "actual_rf_hz")
            )
        )
        outcome = (
            "both_receivers_candidate_present"
            if states == {"observed_candidate_present"}
            else "both_receivers_candidate_absent"
            if states == {"observed_candidate_absent"}
            else "receiver_probe_incomplete"
            if {"missing_receiver_probe", "duplicate_receiver_probe"} & states
            else "unqualified_opportunity"
            if {"unqualified_input", "unqualified_timing"} & states
            else "one_receiver_candidate_present"
        )
        if not pair_consistent and outcome != "receiver_probe_incomplete":
            outcome = "inconsistent_receiver_pair"
        time = _time(raw, primary)
        if time["window_start_utc_ns"] is None and outcome != "receiver_probe_incomplete":
            outcome = "source_timing_unavailable"
        rows.append(
            {
                "schema": "rx-paired-opportunity/v1",
                "source_window_id": window_id,
                "split": split,
                "cache_sha256": cache_sha256,
                "source_window": source,
                "satellite_id": None,
                "opportunity_status": outcome,
                "source_qualification": {
                    "input_qualified": bool(_get(raw, "qualified", False)),
                    "timing_qualified": bool(_get(_get(raw, "timing"), "qualified", False)),
                    "timestamp_present": time["window_start_utc_ns"] is not None,
                    "receiver_probe_count": {
                        "rx0": len(receivers.get(0, [])),
                        "rx1": len(receivers.get(1, [])),
                    },
                },
                "receivers": views,
                **time,
            }
        )
    return rows, bindings


def _load_verified(entry: dict[str, Any]) -> Any:
    payload = Path(entry["cache_file"]).read_bytes()
    if "sha256:" + hashlib.sha256(payload).hexdigest() != entry["cache_sha256"]:
        raise ValueError(f"{entry['session_id']}: cache digest mismatch")
    raw = pickle.loads(payload)
    for name in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
        if _get(raw, name) != entry[name]:
            raise ValueError(f"{entry['session_id']}: {name} mismatch")
    return raw


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def export_inventory(inventory_path: Path, output_dir: Path) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=False)
    opportunities: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for entry in inventory:
        if entry.get("ready"):
            raw = _load_verified(entry)
            rows, sources = export_input(
                raw,
                split=entry["split"],
                cache_sha256=entry["cache_sha256"],
                projected=projected_candidates(raw),
            )
            opportunities.extend(rows)
            bindings.extend(sources)
    _write(output_dir / "opportunities.jsonl", opportunities)
    _write(output_dir / "source-bindings.jsonl", bindings)
    summary = {
        "schema": "rx-paired-opportunity-export-summary/v1",
        "inventory": str(inventory_path),
        "opportunity_count": len(opportunities),
        "source_binding_count": len(bindings),
        "opportunity_status_counts": dict(
            sorted(Counter(x["opportunity_status"] for x in opportunities).items())
        ),
        "satellite_identity": "unassigned; satellite_id is null in every evidence row",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_inventory(args.inventory, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
