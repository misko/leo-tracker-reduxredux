#!/usr/bin/env python3
"""Run the frozen small matched-window CFO comparison through public read ports."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def summarize_held(rows: list[dict], receiver: int, method: str) -> dict:
    """Fit two training points and evaluate held rows without held-value fitting."""
    subset = [row for row in rows if row["receiver_id"] == receiver and row["method"] == method]
    train = [row for row in subset if row["training"] and row["state"] == "supported"]
    held = [row for row in subset if not row["training"] and row["state"] == "supported"]
    if len(train) != 2 or not held:
        return {
            "receiver_id": receiver,
            "method": method,
            "state": "inapplicable",
            "reason": "need two supported train and one held window",
        }
    train.sort(key=lambda row: row["support_center_utc_ns"])
    times = np.asarray([row["support_center_utc_ns"] / 1e9 for row in train])
    values = np.asarray([row["cfo_hz"] for row in train])
    slope = (values[1] - values[0]) / (times[1] - times[0])
    errors = [
        row["cfo_hz"] - (values[0] + slope * (row["support_center_utc_ns"] / 1e9 - times[0]))
        for row in held
    ]
    return {
        "receiver_id": receiver,
        "method": method,
        "state": "supported",
        "train_count": 2,
        "held_count": len(errors),
        "held_errors_hz": errors,
        "held_rms_hz": float(np.sqrt(np.mean(np.square(errors)))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.analysis.qam.pilot import analyze_pilot_phase_slope

    started = time.monotonic()
    spec = json.loads(args.spec.read_text())
    metadata = ScannerTrackingInputStore(args.bulk_root)
    try:
        raw = metadata.load(spec["session_id"])
    finally:
        metadata.close()
    probes = {(p.visit_index, p.receiver_id, p.probe_index): p for p in raw.probes}
    projected = {point.candidate_id: point for point in project_scanner_candidates(raw)}
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    published = store.inspect(spec["session_id"])
    if published.manifest_sha256 != spec["manifest_sha256"]:
        raise ValueError("source manifest changed")
    reader = store.reader(spec["session_id"], expected=published)
    visits = {}
    actual_bytes = 0
    try:
        for visit_index in sorted({row["visit_index"] for row in spec["windows"]}):
            visit, ci16 = reader.read_visit_ci16(visit_index)
            visits[visit_index] = (visit, ci16)
            actual_bytes += ci16.nbytes
    finally:
        reader.close()
        store.close()
    if actual_bytes > spec["iq_limit_bytes"]:
        raise RuntimeError("public visit reads exceeded frozen IQ limit")
    rows = []
    for window in spec["windows"]:
        probe = probes[(window["visit_index"], window["receiver_id"], window["probe_index"])]
        point = projected.get(window["candidate_id"])
        if point is None:
            raise ValueError("frozen candidate ID is absent")
        matching = [
            item for item in probe.candidates if item.candidate_rank == point.candidate_rank
        ]
        if len(matching) != 1:
            raise ValueError("frozen candidate rank is not unique within its probe")
        candidate = matching[0]
        if candidate.fractional_tracking_cfo_hz != window["acquisition_bound_cfo_hz"]:
            raise ValueError("frozen candidate CFO changed")
        visit, ci16 = visits[window["visit_index"]]
        visit_start = window["visit_index"] * ci16.shape[0]
        local_start = probe.payload_start_sample - visit_start
        count = round(raw.probe_ms * raw.sample_rate_hz / 1000)
        packed = ci16[local_start : local_start + count, window["receiver_id"]]
        samples = packed[:, 0].astype(float) + 1j * packed[:, 1].astype(float)
        phase = analyze_pilot_phase_slope(
            samples,
            raw.sample_rate_hz,
            epoch_sample=int(
                round(candidate.integer_epoch_sample + candidate.fractional_epoch_offset_samples)
            ),
            absolute_cfo_hz=window["acquisition_bound_cfo_hz"],
            edge=window["edge"],
        )
        base = {
            "candidate_id": window["candidate_id"],
            "visit_index": window["visit_index"],
            "receiver_id": window["receiver_id"],
            "support_center_utc_ns": window["support_center_utc_ns"],
            "training": window["baseline_training_mask"],
            "candidate_rank": candidate.candidate_rank,
            "integer_epoch_sample": candidate.integer_epoch_sample,
            "fractional_epoch_offset_samples": candidate.fractional_epoch_offset_samples,
        }
        rows.append(
            {
                **base,
                "method": "baseline",
                "state": "supported",
                "cfo_hz": window["acquisition_bound_cfo_hz"],
            }
        )
        frame_values = np.asarray([frame.absolute_cfo_hz for frame in phase.frames], dtype=float)
        state = "supported" if frame_values.size else "rejected"
        reason = None if frame_values.size else phase.reason
        rows.append(
            {
                **base,
                "method": "ordinary_profile",
                "state": state,
                "reason": reason,
                "cfo_hz": float(np.mean(frame_values)) if frame_values.size else None,
            }
        )
        rows.append(
            {
                **base,
                "method": "robust_profile",
                "state": state,
                "reason": reason,
                "cfo_hz": float(np.median(frame_values)) if frame_values.size else None,
            }
        )
        rows.append(
            {
                **base,
                "method": "differential_phase",
                "state": state,
                "reason": reason,
                "cfo_hz": phase.aggregate_absolute_cfo_hz if frame_values.size else None,
                "frame_count": len(phase.frames),
            }
        )
    summaries = []
    for receiver in (0, 1):
        for method in spec["methods"]:
            summaries.append(summarize_held(rows, receiver, method))
    output = {
        "schema": "ds7-cfo-wave2-result/v1",
        "session_id": spec["session_id"],
        "manifest_sha256": spec["manifest_sha256"],
        "spec_path": str(args.spec),
        "actual_iq_bytes": actual_bytes,
        "elapsed_seconds": time.monotonic() - started,
        "rows": rows,
        "summaries": summaries,
        "limitations": [
            "small pre-score subset",
            "two training visits define each receiver line exactly",
            "candidate-only known edge pilots",
            "no geographic fit or reference access",
        ],
    }
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
