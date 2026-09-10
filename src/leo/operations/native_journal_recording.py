"""Read-only application adapter for closed native-refinement recording exports."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from leo.contracts.native_journal_recording import NativeJournalRecordingV1


def load_native_recording(path: Path, *, expected_sha256: str) -> NativeJournalRecordingV1:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("native recording requires an exact expected file digest")
    with path.open("rb") as stream:
        raw = stream.read(256 * 1024 * 1024 + 1)
    if len(raw) > 256 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("native recording exceeds its bound or differs from expected bytes")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate native recording JSON field")
            result[key] = value
        return result

    # Reject duplicate keys before the typed parser could choose the last one.
    json.loads(raw, object_pairs_hook=unique)
    return NativeJournalRecordingV1.model_validate_json(raw)


def recording_review(recording: NativeJournalRecordingV1) -> tuple[dict, list[dict]]:
    measurements = recording.measurements
    anchor = int(measurements[0].native_start_sample) if measurements else 0
    rows = []
    rejections: dict[str, int] = {}
    for measurement in measurements:
        start = int(measurement.native_start_sample)
        # Preserve sub-sample precision even when the source counter exceeds 2**53.
        relative = (start - anchor) / recording.source_rate_hz
        rows.append(
            {
                "sequence": measurement.sequence,
                "frame": measurement.frame,
                "native_start_sample": measurement.native_start_sample,
                "relative_scheduled_start_s": relative,
                "relative_refined_start_s": relative + measurement.delay_s,
                "delay_s": measurement.delay_s,
                "cfo_hz": measurement.cfo_hz,
                "residual_hz": measurement.residual_hz,
                "coherence": measurement.coherence,
                "supported": measurement.supported,
                "rejection": measurement.rejection,
                "hardware_fault": measurement.hardware_fault,
            }
        )
        if not measurement.supported:
            key = str(measurement.rejection)
            rejections[key] = rejections.get(key, 0) + 1
    supported = [measurement.cfo_hz for measurement in measurements if measurement.supported]
    summary = {
        "schema": "native-journal-application-review/v1",
        "journal_sha256": recording.journal_sha256,
        "epoch": recording.epoch,
        "source_rate_hz": recording.source_rate_hz,
        "pilot_samples": recording.pilot_samples,
        "native_sample_anchor": str(anchor) if measurements else None,
        "head_count": recording.head_count,
        "supported_count": recording.supported_count,
        "rejected_count": recording.rejected_count,
        "rejection_mask_counts": rejections,
        "supported_cfo_min_hz": min(supported) if supported else None,
        "supported_cfo_max_hz": max(supported) if supported else None,
        "observed_start_span_s": rows[-1]["relative_scheduled_start_s"] if rows else None,
        "frequency_reference": recording.frequency_reference,
        "timing_reference": recording.timing_reference,
        "radio_boot_source_bound": False,
        "acquisition_verified": False,
        "solver_replayed": False,
        "original_native_iq_verified": False,
        "physical_precision_qualified": False,
        "runtime_outcome": "not_supplied_by_journal_port",
        "drained": recording.drained.model_dump(mode="json"),
        "final": recording.final.model_dump(mode="json"),
    }
    return summary, rows


def review_native_recording(path: Path, output: Path, *, expected_sha256: str) -> dict:
    recording = load_native_recording(path, expected_sha256=expected_sha256)
    summary, rows = recording_review(recording)
    summary["recording_export_sha256"] = expected_sha256
    output.mkdir(parents=True, exist_ok=False)
    with (output / "measurements.csv").open("x", newline="") as stream:
        columns = (
            "sequence",
            "frame",
            "native_start_sample",
            "relative_scheduled_start_s",
            "relative_refined_start_s",
            "delay_s",
            "cfo_hz",
            "residual_hz",
            "coherence",
            "supported",
            "rejection",
            "hardware_fault",
        )
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with (output / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return summary
