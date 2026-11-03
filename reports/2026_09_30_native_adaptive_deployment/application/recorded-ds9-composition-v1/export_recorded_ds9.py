#!/usr/bin/env python3
"""Export hash-bound public DS9 visits for the recorded scanner composition."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

SESSION = "scan-fw-3cfdaa6d75762cad"
STORE_MANIFEST = "sha256:5b8755586b9a84444ea3caf1bcb5cb0f6c6d80b7c9e3087666331608883de2bd"
FROZEN_CAPTURE_MANIFEST = "13ef58d3af534eb3cfe1a3ca96595eb59000dd6d4a8438848d47b435bed4aa52"
RECORDED_TRANSITION_FLAGS = 0x1 | 0x2 | 0x8


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tsv_field(value: object) -> str:
    if isinstance(value, bool):
        text = "1" if value else "0"
    else:
        text = str(value)
    if "\t" in text or "\n" in text or "\r" in text:
        raise ValueError("native TSV field contains a delimiter")
    return text


def native_tsv(bundle: dict) -> str:
    session = bundle["session"]
    timing = session["timing"]
    calibration = bundle["calibration"]
    lines = [["FORMAT", "leo-recorded-ds9/v1"]]
    lines.append([
        "SESSION", session["session_id"], session["scanner_session"],
        session["generation"], session["sample_rate_hz"], session["receiver_count"],
        calibration["analog_bandwidth_hz"], session["recording_manifest_sha256"],
        session["calibration_manifest_sha256"], bundle["plan_digest"],
    ])
    lines.append([
        "TIMING", timing["qualified"], timing["monotonic_before_ns"],
        timing["monotonic_after_ns"], timing["anchor_counter"],
        timing["utc_before_ns"], timing["utc_after_ns"], timing["bracket_width_ns"],
    ])
    for target in calibration["targets"]:
        lines.append([
            "TARGET", target["target_index"], target["target_key"], target["channel"],
            target["edge"], target["requested_tuned_if_hz"],
            target["actual_tuned_if_hz"], target["actual_rf_hz"],
            target["pilot_if_hz"][0], target["pilot_if_hz"][1],
            target["template_min_hz"], target["template_max_hz"],
            target["profile_crc32"],
        ])
    visit_fields = (
        "visit", "target_index", "target_key", "dwell_ms", "selection_applied",
        "expected_transition_flags", "expected_profile_crc32",
        "requested_frequency_hz", "expected_actual_frequency_hz",
        "selection_counter", "transition_previous_valid_end",
        "transition_valid_start", "valid_start", "valid_end",
    )
    for visit in bundle["visits"]:
        lines.append([
            "VISIT", *(visit[field] for field in visit_fields),
            visit["recording_event_sha256"], visit["raw_sha256"],
            visit["raw_bytes"], visit["raw_path"],
        ])
    return "".join("\t".join(tsv_field(value) for value in row) + "\n" for row in lines)


def selected_visits(scope: str, selection: Path) -> list[int]:
    if scope == "visit301":
        return [301]
    document = json.loads(selection.read_text())
    if document.get("schema") != "org.leo.ds9-corrected-wrapper-slice-selection/v1":
        raise ValueError("unexpected balanced selection schema")
    visits = [int(item["visit"]) for item in document["visits"]]
    if len(visits) != 32 or len(set(visits)) != len(visits):
        raise ValueError("balanced selection must contain 32 distinct visits")
    return sorted(visits)


def target_calibrations(manifest: dict, selected_events: list[dict]) -> list[dict]:
    from leo.analysis.starlink.templates import edge_frequencies_hz
    from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz

    geometry = manifest["receipt"]["plan"]["geometry"]
    selected_targets = {int(event["target_index"]) for event in selected_events}
    profiles = {int(item["target_index"]): item for item in geometry["profiles"]}
    result = []
    for target_index in sorted(selected_targets):
        profile = profiles[target_index]
        target = profile["target"]
        events = [event for event in selected_events if event["target_index"] == target_index]
        event_values = {
            (
                int(event["fastlock_slot"]),
                int(event["actual_lo_frequency_hz"]),
                int(event["target"]["channel"]),
                event["target"]["edge"],
                int(event["target"]["if_center_hz"]),
                int(event["target"]["rf_center_hz"]),
            )
            for event in events
        }
        if len(event_values) != 1:
            raise ValueError(f"target calibration varies within target {target_index}")
        profile_key, actual_if, channel, edge, requested_if, actual_rf = event_values.pop()
        if profile_key != int(profile["fastlock_profile_index"]) or target != events[0]["target"]:
            raise ValueError("event target differs from capture plan")
        offsets = np.asarray(edge_frequencies_hz(edge), dtype=np.float64)
        pilot_if = int(starlink_edge_rf_center_frequency_hz(channel, edge)) - int(
            geometry["lnb_lo_hz"]
        )
        result.append(
            {
                "target_index": target_index,
                "target_key": profile_key,
                "channel": channel,
                "edge": edge,
                "requested_tuned_if_hz": requested_if,
                "actual_tuned_if_hz": actual_if,
                "actual_rf_hz": actual_rf,
                "pilot_if_hz": [pilot_if, pilot_if],
                "template_min_hz": float(offsets.min()),
                "template_max_hz": float(offsets.max()),
                "profile_crc32": 0,
            }
        )
    return result


def export(scope: str, output: Path, bulk_root: str, selection: Path) -> dict:
    output = output.resolve()
    qnap = Path("/mnt/qnap01").resolve()
    if output == qnap or qnap in output.parents:
        raise ValueError("recorded export output must not be beneath /mnt/qnap01")
    if output.exists():
        raise FileExistsError("recorded export refuses an existing destination")
    from leo.analysis.starlink import templates
    from leo.contracts import starlink_frequency
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    visits = selected_visits(scope, selection)
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    session = store.inspect(SESSION)
    manifest = session.manifest.model_dump(mode="json")
    public_manifest = json.loads(
        Path(
            "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "location-source-inventory/capture-manifest.json"
        ).read_text()
    )
    frozen_manifest_path = Path(
        "reports/2026_09_30_native_adaptive_deployment/ds9/"
        "location-source-inventory/capture-manifest.json"
    )
    if (manifest != public_manifest or session.manifest_sha256 != STORE_MANIFEST or
            file_sha256(frozen_manifest_path) != FROZEN_CAPTURE_MANIFEST):
        raise ValueError("public store manifest differs from frozen capture manifest")
    events_by_visit = {
        int(event["visit_index"]): event for event in manifest["receipt"]["events"]
    }
    if any(visit not in events_by_visit for visit in visits):
        raise ValueError("selected visit is absent from capture manifest")
    selected_events = [events_by_visit[visit] for visit in visits]
    calibration = target_calibrations(manifest, selected_events)
    calibration_document = {
        "schema": "org.leo.recorded-calibration/v1",
        "sample_rate_hz": int(manifest["receipt"]["plan"]["geometry"]["sample_rate_hz"]),
        "receiver_count": len(manifest["receipt"]["plan"]["geometry"]["receiver_ids"]),
        "analog_bandwidth_hz": int(manifest["receipt"]["plan"]["geometry"]["bandwidth_hz"]),
        "targets": calibration,
        "contract_sources": {
            "starlink_frequency.py": file_sha256(Path(inspect.getsourcefile(starlink_frequency))),
            "templates.py": file_sha256(Path(inspect.getsourcefile(templates))),
        },
    }
    calibration_document["manifest_sha256"] = canonical_sha256(calibration_document)
    timing = manifest["timing"]
    scanner_session = int(manifest["receipt"]["terminal"]["session_id"])
    session_document = {
        "session_id": SESSION,
        "scanner_session": scanner_session,
        "generation": int(manifest["receipt"]["stream_generation"]),
        "sample_rate_hz": calibration_document["sample_rate_hz"],
        "receiver_count": calibration_document["receiver_count"],
        "sample_format": "ci16-le",
        "sample_layout": "sample,receiver,iq",
        "recording_manifest_sha256": session.manifest_sha256.removeprefix("sha256:"),
        "calibration_manifest_sha256": calibration_document["manifest_sha256"],
        "timing": {
            "qualified": bool(timing["qualified"]),
            "anchor_counter": int(timing["session_start_device_sample_counter"]),
            "utc_before_ns": int(timing["first_sample_earliest_utc_ns"]),
            "utc_after_ns": int(timing["first_sample_latest_utc_ns"]),
            "monotonic_before_ns": int(timing["begin_before_monotonic_ns"]),
            "monotonic_after_ns": int(timing["begin_after_monotonic_ns"]),
            "bracket_width_ns": int(timing["first_sample_bracket_width_ns"]),
        },
    }
    if not session_document["timing"]["qualified"]:
        raise ValueError("capture timing is not qualified")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    try:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        rows = []
        with store.reader(SESSION, expected=session) as reader:
            for visit_index in visits:
                visit, values = reader.read_visit_ci16(visit_index)
                event = visit.event.model_dump(mode="json")
                expected = events_by_visit[visit_index]
                if event != expected:
                    raise ValueError(f"public event changed at visit {visit_index}")
                start = int(event["valid_start_counter"])
                end = int(event["valid_end_counter_exclusive"])
                rate = session_document["sample_rate_hz"]
                if end - start != rate * 120 // 1000:
                    raise ValueError("recorded composition v1 accepts only 120 ms visits")
                raw = np.asarray(values, dtype="<i2", order="C").tobytes(order="C")
                expected_bytes = (end - start) * session_document["receiver_count"] * 2 * 2
                if len(raw) != expected_bytes:
                    raise ValueError("raw visit shape differs from counter interval")
                raw_name = f"visit-{visit_index:06d}.ci16"
                raw_path = raw_dir / raw_name
                raw_path.write_bytes(raw)
                decision = event["decision"]
                if int(decision["proposed_target"]) != int(event["target_index"]):
                    raise ValueError("recorded decision target differs from applied target")
                rows.append(
                    {
                        "visit": visit_index,
                        "target_index": int(event["target_index"]),
                        "target_key": int(event["fastlock_slot"]),
                        "dwell_ms": 120,
                        "selection_applied": 1,
                        "expected_transition_flags": RECORDED_TRANSITION_FLAGS,
                        "expected_profile_crc32": 0,
                        "requested_frequency_hz": int(event["target"]["if_center_hz"]),
                        "expected_actual_frequency_hz": int(event["actual_lo_frequency_hz"]),
                        "selection_counter": int(decision["decision_counter"]),
                        "transition_previous_valid_end": int(event["invalid_start_counter"]),
                        "transition_valid_start": start,
                        "transition_before_counter": int(event["transition_before_counter"]),
                        "transition_after_counter": int(event["transition_after_counter"]),
                        "valid_start": start,
                        "valid_end": end,
                        "device_event_sequence": int(event["event_sequence"]),
                        "device_event_id": int(event["device_event_id"]),
                        "device_event_flags": int(event["device_event_flags"]),
                        "policy_generation": int(decision["generation"]),
                        "recording_event_sha256": canonical_sha256(event),
                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "raw_bytes": len(raw),
                        "raw_path": f"raw/{raw_name}",
                        "public_store": {
                            "adapter": "leo.storage.adaptive_hop.AdaptiveHopIqStore",
                            "read_only": True,
                            "session_id": SESSION,
                            "visit": visit_index,
                        },
                    }
                )
        for previous, current in zip(rows, rows[1:]):
            if current["visit"] <= previous["visit"] or current["valid_start"] < previous["valid_end"]:
                raise ValueError("recorded plan is not ordered and nonoverlapping")
        plan_material = {
            "schema": "org.leo.scanner-recorded-plan/v1",
            "session": session_document,
            "calibration": calibration_document,
            "visits": rows,
        }
        bundle = dict(plan_material)
        bundle["plan_digest"] = canonical_sha256(plan_material)
        bundle["persisted_candidate_values_used_in_plan"] = False
        bundle["adaptive_policy_replayed"] = False
        bundle["scope"] = scope
        (staging / "bundle.json").write_text(json.dumps(bundle, indent=2) + "\n")
        (staging / "native.tsv").write_text(native_tsv(bundle))
        files = {
            str(path.relative_to(staging)): file_sha256(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        (staging / "SHA256SUMS.json").write_text(json.dumps(files, indent=2) + "\n")
        for directory in (staging, raw_dir):
            directory.chmod(0o755)
        for path in staging.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        os.replace(staging, output)
        return bundle
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("visit301", "panel32"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", default="/srv/bulk/leo")
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path(
            "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "corrected-full-replay-v1/selection.json"
        ),
    )
    args = parser.parse_args()
    result = export(args.scope, args.output, args.bulk_root, args.selection)
    print(json.dumps({"scope": args.scope, "visits": len(result["visits"]),
        "plan_digest": result["plan_digest"], "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
