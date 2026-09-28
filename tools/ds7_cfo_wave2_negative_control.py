#!/usr/bin/env python3
"""Score a frozen symbol-phase negative control on one held DS7 visit."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbol_phase_scramble(
    matched: np.ndarray, *, seed: int, candidate_id: str, frame_index: int
) -> np.ndarray:
    """Apply deterministic symbol-varying QPSK phase across every tone."""
    identity = f"{seed}:{candidate_id}:{frame_index}".encode()
    local_seed = int.from_bytes(hashlib.sha256(identity).digest()[:16], "big")
    rng = np.random.default_rng(local_seed)
    indexes = rng.integers(0, 4, size=len(matched))
    phases = np.exp(0.5j * np.pi * indexes)
    return np.asarray(matched, dtype=np.complex128) * phases[:, None]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()

    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.analysis.qam.pilot import _complete_frame_starts, _KnownPilotDemodulator
    from leo.analysis.research.frame_cfo import (
        differential_phase_cfo,
        ordinary_profile_cfo,
        profiled_coherence,
        robust_profile_cfo,
    )
    from leo.analysis.starlink import OFDM_SYMBOL_DURATION_S, StarlinkEdge, qin_edge_pilot_symbols

    started = time.monotonic()
    spec = json.loads(args.spec.read_text())
    profile_path = Path(spec["source_profile_result"])
    audit_path = Path(spec["lane_audit"])
    if sha256(profile_path) != spec["source_profile_result_sha256"]:
        raise ValueError("profile result digest changed")
    if sha256(audit_path) != spec["lane_audit_sha256"]:
        raise ValueError("lane audit digest changed")
    profile = json.loads(profile_path.read_text())
    read_spec = json.loads(Path("reports/2026_09_27_ds7_wave2/cfo/read-spec-v2.json").read_text())
    held_windows = {
        row["receiver_id"]: row
        for row in read_spec["windows"]
        if row["visit_index"] == spec["held_visit"]
    }
    frozen_receivers = {row["receiver_id"]: row for row in spec["receivers"]}
    if set(held_windows) != set(frozen_receivers):
        raise ValueError("held receiver support changed")
    for receiver, window in held_windows.items():
        frozen = frozen_receivers[receiver]
        binding = (window["candidate_id"], window["channel"], window["actual_rf_hz"])
        expected = (frozen["candidate_id"], frozen["channel"], frozen["actual_rf_hz"])
        if binding != expected:
            raise ValueError("held lane or candidate binding changed")

    metadata = ScannerTrackingInputStore(args.bulk_root)
    try:
        raw = metadata.load(spec["session_id"])
    finally:
        metadata.close()
    if raw.input_manifest_sha256 != spec["manifest_sha256"]:
        raise ValueError("metadata manifest changed")
    probes = {(p.visit_index, p.receiver_id, p.probe_index): p for p in raw.probes}
    points = {point.candidate_id: point for point in project_scanner_candidates(raw)}

    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    published = store.inspect(spec["session_id"])
    if published.manifest_sha256 != spec["manifest_sha256"]:
        raise ValueError("IQ manifest changed")
    reader = store.reader(spec["session_id"], expected=published)
    try:
        _, ci16 = reader.read_visit_ci16(spec["held_visit"])
    finally:
        reader.close()
        store.close()
    if ci16.nbytes > spec["iq_limit_bytes"]:
        raise RuntimeError("IQ read exceeded frozen limit")

    times = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times -= np.mean(times)
    even = np.arange(0, 300, 2, dtype=int)
    score_rows = []
    for receiver, window in held_windows.items():
        point = points[window["candidate_id"]]
        probe = probes[(window["visit_index"], receiver, window["probe_index"])]
        candidates = [c for c in probe.candidates if c.candidate_rank == point.candidate_rank]
        if len(candidates) != 1:
            raise ValueError("held candidate rank is not unique")
        candidate = candidates[0]
        local_start = probe.payload_start_sample - spec["held_visit"] * ci16.shape[0]
        count = round(raw.probe_ms * raw.sample_rate_hz / 1000)
        packed = ci16[local_start : local_start + count, receiver]
        samples = packed[:, 0].astype(float) + 1j * packed[:, 1].astype(float)
        epoch = round(candidate.integer_epoch_sample + candidate.fractional_epoch_offset_samples)
        starts = _complete_frame_starts(len(samples), raw.sample_rate_hz, epoch)
        demodulator = _KnownPilotDemodulator(
            samples,
            raw.sample_rate_hz,
            StarlinkEdge(window["edge"]),
            window["acquisition_bound_cfo_hz"],
        )
        known = qin_edge_pilot_symbols(StarlinkEdge(window["edge"]))[even]
        matrices = [demodulator.frame(start)[even] * np.conj(known) for start in starts]
        predictions = {
            row["method"]: row["predicted_cfo_hz"]
            for row in profile["held_scores"]
            if row["visit_index"] == spec["held_visit"] and row["receiver_id"] == receiver
        }
        if set(predictions) != set(spec["methods"]):
            raise ValueError("fixed real-training predictions are incomplete")
        scrambled = [
            symbol_phase_scramble(
                matrix,
                seed=spec["control"]["seed"],
                candidate_id=window["candidate_id"],
                frame_index=index,
            )
            for index, matrix in enumerate(matrices)
        ]
        for method in spec["methods"]:
            residual = predictions[method] - window["acquisition_bound_cfo_hz"]
            if abs(residual) > 2000.0:
                raise ValueError("fixed prediction left the frozen acquisition basin")
            if method == "ordinary_profile":
                estimates = [
                    ordinary_profile_cfo(
                        matrix,
                        times[even],
                        maximum_residual_cfo_hz=2000.0,
                        coarse_step_hz=100.0,
                        fine_step_hz=5.0,
                    )
                    for matrix in matrices
                ]
                boundary_count = sum(item.search_boundary for item in estimates)
            elif method == "robust_profile":
                estimates = [
                    robust_profile_cfo(
                        matrix,
                        times[even],
                        maximum_residual_cfo_hz=2000.0,
                        coarse_step_hz=100.0,
                        fine_step_hz=5.0,
                        maximum_iterations=4,
                    )
                    for matrix in matrices
                ]
                boundary_count = sum(item.search_boundary for item in estimates)
            elif method == "differential_phase":
                estimates = [
                    differential_phase_cfo(matrix, times[even], maximum_residual_cfo_hz=2000.0)
                    for matrix in matrices
                ]
                boundary_count = sum(abs(item) >= 2000.0 - 1e-6 for item in estimates)
            else:
                boundary_count = 0
            real = np.asarray([profiled_coherence(m, times[even], residual) for m in matrices])
            control = np.asarray([profiled_coherence(m, times[even], residual) for m in scrambled])
            score_rows.append(
                {
                    "receiver_id": receiver,
                    "visit_index": spec["held_visit"],
                    "method": method,
                    "state": "supported" if boundary_count == 0 else "rejected",
                    "boundary_frame_count": int(boundary_count),
                    "fixed_prediction_cfo_hz": predictions[method],
                    "frame_count": len(matrices),
                    "real_mean_profiled_coherence": float(np.mean(real)),
                    "scrambled_mean_profiled_coherence": float(np.mean(control)),
                    "real_minus_scrambled": float(np.mean(real) - np.mean(control)),
                }
            )
    output = {
        "schema": "ds7-cfo-wave2-negative-control-result/v1",
        "spec_sha256": sha256(args.spec),
        "session_id": spec["session_id"],
        "actual_iq_bytes": ci16.nbytes,
        "elapsed_seconds": time.monotonic() - started,
        "rows": score_rows,
        "excluded": [spec["excluded_visit"]],
        "claim_scope": (
            "tiny deterministic negative diagnostic; "
            "not calibrated false-positive performance"
        ),
        "reference_audit": "reference_excluded",
    }
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
