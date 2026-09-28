#!/usr/bin/env python3
"""Run frozen true profile-CFO methods and a common held waveform objective."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _line_prediction(rows: list[dict], receiver: int, method: str, held_time_ns: int) -> float:
    train = sorted(
        (
            row
            for row in rows
            if row["receiver_id"] == receiver
            and row["method"] == method
            and row["training"]
            and row["state"] == "supported"
        ),
        key=lambda row: row["support_center_utc_ns"],
    )
    if len(train) != 2:
        raise ValueError("each prediction requires exactly two supported training windows")
    t0, t1 = (row["support_center_utc_ns"] / 1e9 for row in train)
    y0, y1 = (row["cfo_hz"] for row in train)
    return float(y0 + (y1 - y0) / (t1 - t0) * (held_time_ns / 1e9 - t0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()

    from leo.analysis.qam.pilot import _KnownPilotDemodulator, _complete_frame_starts
    from leo.analysis.research.frame_cfo import (
        differential_phase_cfo,
        ordinary_profile_cfo,
        profiled_coherence,
        robust_profile_cfo,
    )
    from leo.analysis.starlink import OFDM_SYMBOL_DURATION_S, StarlinkEdge, qin_edge_pilot_symbols
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    started = time.monotonic()
    spec = json.loads(args.spec.read_text())
    base_path = Path(spec["base_spec_path"])
    if _sha256(base_path) != spec["base_spec_sha256"]:
        raise ValueError("base spec digest changed")
    base = json.loads(base_path.read_text())
    metadata = ScannerTrackingInputStore(args.bulk_root)
    try:
        raw = metadata.load(spec["session_id"])
    finally:
        metadata.close()
    if raw.input_manifest_sha256 != spec["manifest_sha256"]:
        raise ValueError("metadata manifest changed")
    probes = {(p.visit_index, p.receiver_id, p.probe_index): p for p in raw.probes}
    points = {p.candidate_id: p for p in project_scanner_candidates(raw)}

    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    published = store.inspect(spec["session_id"])
    if published.manifest_sha256 != spec["manifest_sha256"]:
        raise ValueError("IQ manifest changed")
    reader = store.reader(spec["session_id"], expected=published)
    visits = {}
    actual_bytes = 0
    try:
        for visit_index in sorted({row["visit_index"] for row in base["windows"]}):
            visit, ci16 = reader.read_visit_ci16(visit_index)
            visits[visit_index] = (visit, ci16)
            actual_bytes += ci16.nbytes
    finally:
        reader.close()
        store.close()
    if actual_bytes > spec["remaining_iq_limit_bytes"]:
        raise RuntimeError("IQ read exceeded remaining lease")

    times = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times -= np.mean(times)
    even = np.arange(0, 300, 2, dtype=int)
    rows: list[dict] = []
    held_matrices: dict[tuple[int, int], list[np.ndarray]] = {}
    for window in base["windows"]:
        point = points[window["candidate_id"]]
        probe = probes[(window["visit_index"], window["receiver_id"], window["probe_index"])]
        candidates = [c for c in probe.candidates if c.candidate_rank == point.candidate_rank]
        if len(candidates) != 1:
            raise ValueError("frozen candidate rank is not unique")
        candidate = candidates[0]
        _, ci16 = visits[window["visit_index"]]
        local_start = probe.payload_start_sample - window["visit_index"] * ci16.shape[0]
        count = round(raw.probe_ms * raw.sample_rate_hz / 1000)
        packed = ci16[local_start : local_start + count, window["receiver_id"]]
        samples = packed[:, 0].astype(float) + 1j * packed[:, 1].astype(float)
        epoch = int(round(candidate.integer_epoch_sample + candidate.fractional_epoch_offset_samples))
        starts = _complete_frame_starts(len(samples), raw.sample_rate_hz, epoch)
        demodulator = _KnownPilotDemodulator(
            samples, raw.sample_rate_hz, StarlinkEdge(window["edge"]), window["acquisition_bound_cfo_hz"]
        )
        expected = qin_edge_pilot_symbols(StarlinkEdge(window["edge"]))
        matrices = [demodulator.frame(start)[even] * np.conj(expected[even]) for start in starts]
        base_row = {
            "visit_index": window["visit_index"],
            "receiver_id": window["receiver_id"],
            "support_center_utc_ns": window["support_center_utc_ns"],
            "training": window["baseline_training_mask"],
            "frame_count": len(matrices),
        }
        estimates: dict[str, list[float]] = {method: [] for method in spec["methods"]}
        estimates["baseline"] = [window["acquisition_bound_cfo_hz"]]
        for matched in matrices:
            ordinary = ordinary_profile_cfo(matched, times[even], maximum_residual_cfo_hz=2000.0)
            robust = robust_profile_cfo(matched, times[even], maximum_residual_cfo_hz=2000.0)
            differential = differential_phase_cfo(
                matched, times[even], maximum_residual_cfo_hz=2000.0
            )
            acquisition = window["acquisition_bound_cfo_hz"]
            estimates["ordinary_profile"].append(acquisition + ordinary.frequency_hz)
            estimates["robust_profile"].append(acquisition + robust.frequency_hz)
            estimates["differential_phase"].append(acquisition + differential)
        for method, values in estimates.items():
            state = "supported" if values else "rejected"
            rows.append(
                {
                    **base_row,
                    "method": method,
                    "state": state,
                    "cfo_hz": float(np.median(values)) if values else None,
                }
            )
        if not window["baseline_training_mask"]:
            held_matrices[(window["visit_index"], window["receiver_id"])] = matrices

    held_scores = []
    by_window = {(w["visit_index"], w["receiver_id"]): w for w in base["windows"]}
    for key, matrices in held_matrices.items():
        window = by_window[key]
        for method in spec["methods"]:
            predicted = _line_prediction(
                rows, window["receiver_id"], method, window["support_center_utc_ns"]
            )
            residual = predicted - window["acquisition_bound_cfo_hz"]
            coherence = [profiled_coherence(m, times[even], residual) for m in matrices]
            held_scores.append(
                {
                    "visit_index": window["visit_index"],
                    "receiver_id": window["receiver_id"],
                    "method": method,
                    "predicted_cfo_hz": predicted,
                    "mean_profiled_coherence": float(np.mean(coherence)),
                    "frame_count": len(coherence),
                }
            )
    summaries = []
    for receiver in (0, 1):
        for method in spec["methods"]:
            selected = [
                row
                for row in held_scores
                if row["receiver_id"] == receiver and row["method"] == method
            ]
            summaries.append(
                {
                    "receiver_id": receiver,
                    "method": method,
                    "held_window_count": len(selected),
                    "mean_profiled_coherence": float(
                        np.mean([row["mean_profiled_coherence"] for row in selected])
                    ),
                }
            )
    output = {
        "schema": "ds7-cfo-wave2-profile-result/v1",
        "spec_sha256": _sha256(args.spec),
        "session_id": spec["session_id"],
        "actual_iq_bytes": actual_bytes,
        "elapsed_seconds": time.monotonic() - started,
        "rows": rows,
        "held_scores": held_scores,
        "summaries": summaries,
        "claim_scope": "common held-waveform temporal self-consistency; no frequency truth or accuracy",
    }
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
