#!/usr/bin/env python3
"""Checkpointed frame/filter replay over corrected dense acquisitions."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from leo.analysis.qam.pilot import analyze_pilot_phase_slope
from leo.analysis.qam.tracking import (
    PilotPhaseDopplerTrackingConfig,
    analyze_contiguous_pilot_phase_doppler_tracking,
)
from leo.analysis.qam.pilot_pnt_kalman import (
    PilotPntKalmanConfig,
    PilotPntKalmanConfigV2,
    analyze_contiguous_pilot_pnt_kalman,
    analyze_contiguous_pilot_pnt_kalman_v2,
    analyze_contiguous_pilot_pnt_kalman_v3,
)

RATE = 10_000_000
PROBE = 200_000
GATE = 0.025


def primary_candidate(probe: dict) -> dict | None:
    passed = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]
    if not passed:
        return None
    return min(passed, key=lambda c: (-c["fractional_margin"], c["candidate_rank"]))


def plain(value):
    if dataclasses.is_dataclass(value):
        return {field.name: plain(getattr(value, field.name)) for field in dataclasses.fields(value) if field.repr}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def summarize_frames(result) -> dict:
    frames = result.frames
    return {
        "status": result.status.value,
        "reason": result.reason,
        "frame_count": len(frames),
        "supported_frame_count": sum(bool(getattr(f, "measurement_supported", getattr(f, "phase_updated", True))) for f in frames),
        "exact_coherence_median": float(np.median([f.exact_coherence for f in frames])) if frames else None,
        "control_coherence_median": float(np.median([f.control_coherence for f in frames])) if frames else None,
        "coherence_margin_median": float(np.median([f.coherence_margin for f in frames])) if frames else None,
    }


def summarize_pnt(result) -> dict:
    innovations = [f.phase_innovation_modulo_pi_rad for f in result.frames if f.measurement_supported]
    return {"status": result.status.value, "reason": result.reason, "frame_count": len(result.frames), "supported_frame_count": result.supported_frame_count, "reacquisition_count": result.reacquisition_count, "phase_update_count": result.phase_update_count, "phase_innovation_rms_rad": float(np.sqrt(np.mean(np.square(innovations)))) if innovations else None, "phase_lock_qualified": result.phase_lock_qualified}


def run(cache: Path, dense: Path, selection_path: Path, output: Path, limit: int | None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    selection = json.loads(selection_path.read_text())
    selected = {row["visit_index"]: row for row in selection["visits"]}
    files = sorted(dense.glob("visit-*.corrected-dense.json"))
    files = [p for p in files if int(p.name[6:12]) in selected]
    if limit is not None:
        files = files[:limit]
    observations = []
    span_observations = []
    accounting = []
    code_sha = "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    start_time = time.monotonic()
    for path in files:
        acquisition_sha = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        document = json.loads(path.read_text())
        product = document["product"]
        visit = product["visit_index"]
        checkpoint = output / f"visit-{visit:04d}.frame-methods.json"
        if checkpoint.exists():
            prior = json.loads(checkpoint.read_text())
            if prior.get("code_sha256") == code_sha and prior.get("dense_acquisition_sha256") == acquisition_sha:
                observations.extend(prior["observations"])
                span_observations.extend(prior["span_observations"])
                accounting.extend(prior["accounting"])
                continue
        iq = np.load(cache / f"visit-{visit:04d}" / "iq_ci16.npy", mmap_mode="r")
        valid = np.load(cache / f"visit-{visit:04d}" / "valid_mask.npy", mmap_mode="r")
        acquired = 0
        for probe in product["probes"]:
            candidate = primary_candidate(probe)
            base = probe["probe_index"] * PROBE
            if candidate is None:
                accounting.append({"visit_index": visit, "receiver_id": probe["receiver_id"], "probe_index": probe["probe_index"], "disposition": "not_acquired"})
                continue
            if not np.all(valid[base:base + PROBE, probe["receiver_id"]]):
                accounting.append({"visit_index": visit, "receiver_id": probe["receiver_id"], "probe_index": probe["probe_index"], "disposition": "invalid_source_support"})
                continue
            acquired += 1
            raw = iq[base:base + PROBE, probe["receiver_id"]]
            samples = raw[:, 0].astype(np.float32) + 1j * raw[:, 1].astype(np.float32)
            samples = np.ascontiguousarray(samples)
            epoch = int(candidate["integer_epoch_sample"])
            cfo = float(candidate["fractional_tracking_cfo_hz"])
            frac = float(candidate["fractional_epoch_offset_samples"])
            slope = analyze_pilot_phase_slope(samples, RATE, epoch_sample=epoch, absolute_cfo_hz=cfo, edge="upper", fractional_epoch_offset_samples=frac)
            ordinary = analyze_contiguous_pilot_phase_doppler_tracking(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=1))
            modulo_tracking = analyze_contiguous_pilot_phase_doppler_tracking(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=2))
            modulo_v1 = analyze_contiguous_pilot_pnt_kalman(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", initial_fractional_epoch_offset_samples=frac, config=PilotPntKalmanConfig())
            modulo_v2 = analyze_contiguous_pilot_pnt_kalman_v2(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", initial_fractional_epoch_offset_samples=frac, config=PilotPntKalmanConfigV2())
            row = {"visit_index": visit, "split": selected[visit]["split"], "target_index": product["target_index"], "receiver_id": probe["receiver_id"], "probe_index": probe["probe_index"], "probe_start_sample": base, "candidate_rank": candidate["candidate_rank"], "integer_epoch_sample": epoch, "fractional_epoch_offset_samples": frac, "acquired_absolute_cfo_hz": candidate["acquired_cfo_hz"], "glrt_residual_cfo_hz": candidate["fractional_residual_cfo_hz"], "tracking_absolute_cfo_hz": cfo, "fractional_margin": candidate["fractional_margin"], "phase_reference": "raw capture sample gauge within one independently acquired 20 ms probe", "slope": {**summarize_frames(slope), "frames": plain(slope.frames)}, "ordinary_2pi": {**summarize_frames(ordinary), "phase_segment_count": ordinary.phase_segment_count, "phase_reset_count": ordinary.phase_reset_count, "phase_update_count": ordinary.phase_update_count, "frames": plain(ordinary.frames)}, "causal_modulo_pi": {**summarize_frames(modulo_tracking), "phase_segment_count": modulo_tracking.phase_segment_count, "phase_reset_count": modulo_tracking.phase_reset_count, "phase_update_count": modulo_tracking.phase_update_count, "ambiguity_transitions": modulo_tracking.phase_ambiguity_transition_count, "frames": plain(modulo_tracking.frames)}, "modulo_pi_v1": {**summarize_pnt(modulo_v1), "frames": plain(modulo_v1.frames)}, "modulo_pi_v2": {**summarize_pnt(modulo_v2), "frames": plain(modulo_v2.frames)}}
            observations.append(row)
            accounting.append({"visit_index": visit, "receiver_id": probe["receiver_id"], "probe_index": probe["probe_index"], "disposition": "processed", "candidate_rank": candidate["candidate_rank"]})
        if acquired == 0:
            pass
        # Historical 50--120 ms gates are evaluated on actual contiguous
        # within-dwell support, seeded only by the earliest qualifying probe.
        for receiver_id in (0, 1):
            receiver_probes = sorted((p for p in product["probes"] if p["receiver_id"] == receiver_id), key=lambda p: p["probe_index"])
            seeded = next(((p, primary_candidate(p)) for p in receiver_probes if primary_candidate(p) is not None), None)
            if seeded is None:
                continue
            seed_probe, candidate = seeded
            assert candidate is not None
            base = seed_probe["probe_index"] * PROBE
            epoch = int(candidate["integer_epoch_sample"])
            cfo = float(candidate["fractional_tracking_cfo_hz"])
            frac = float(candidate["fractional_epoch_offset_samples"])
            for duration_ms in (50, 75, 80, 100, 120):
                count = duration_ms * RATE // 1000
                if base + count > len(iq) or not np.all(valid[base:base + count, receiver_id]):
                    continue
                raw = iq[base:base + count, receiver_id]
                samples = np.ascontiguousarray(raw[:, 0].astype(np.float32) + 1j * raw[:, 1].astype(np.float32))
                ordinary = analyze_contiguous_pilot_phase_doppler_tracking(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=1))
                modulo = analyze_contiguous_pilot_phase_doppler_tracking(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=2))
                v1 = analyze_contiguous_pilot_pnt_kalman(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", initial_fractional_epoch_offset_samples=frac, config=PilotPntKalmanConfig())
                v2 = analyze_contiguous_pilot_pnt_kalman_v2(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper", initial_fractional_epoch_offset_samples=frac, config=PilotPntKalmanConfigV2())
                span_row = {"visit_index": visit, "split": selected[visit]["split"], "target_index": product["target_index"], "receiver_id": receiver_id, "start_probe_index": seed_probe["probe_index"], "duration_ms": duration_ms, "seed_rule": "earliest corrected-GLRT qualifying probe, independent of phase outcome", "seed_epoch_sample": epoch, "seed_fractional_epoch_offset_samples": frac, "seed_tracking_absolute_cfo_hz": cfo, "ordinary_2pi": {**summarize_frames(ordinary), "phase_reset_count": ordinary.phase_reset_count, "phase_update_count": ordinary.phase_update_count, "frames": plain(ordinary.frames)}, "causal_modulo_pi": {**summarize_frames(modulo), "phase_reset_count": modulo.phase_reset_count, "phase_update_count": modulo.phase_update_count, "ambiguity_transitions": modulo.phase_ambiguity_transition_count, "frames": plain(modulo.frames)}, "pnt_v1": {**summarize_pnt(v1), "frames": plain(v1.frames)}, "pnt_v2": {**summarize_pnt(v2), "frames": plain(v2.frames)}}
                # V3 performs its own full-frame epoch/CFO reacquisition. Run
                # it at the historical 75 ms gate and full available span.
                if duration_ms in (75, 120):
                    v3 = analyze_contiguous_pilot_pnt_kalman_v3(samples, RATE, epoch_sample=epoch, initial_absolute_cfo_hz=cfo, edge="upper")
                    span_row["pnt_v3"] = {**summarize_pnt(v3), "alignment_status": v3.initial_alignment.status.value if v3.initial_alignment else None, "alignment_epoch_sample": v3.initial_alignment.epoch_sample if v3.initial_alignment else None, "alignment_absolute_cfo_hz": v3.initial_alignment.absolute_cfo_hz if v3.initial_alignment else None, "frames": plain(v3.frames)}
                span_observations.append(span_row)
        subset = [x for x in observations if x["visit_index"] == visit]
        span_subset = [x for x in span_observations if x["visit_index"] == visit]
        accounting_subset = [x for x in accounting if x["visit_index"] == visit]
        checkpoint.write_text(json.dumps({"schema": "scan-phase-frame-methods/v2", "input_manifest_sha256": selection["input_manifest_sha256"], "visit_index": visit, "code_sha256": code_sha, "dense_acquisition_sha256": acquisition_sha, "observations": subset, "span_observations": span_subset, "accounting": accounting_subset}, indent=2) + "\n")
    body = {"schema": "scan-phase-frame-methods/v1", "input_manifest_sha256": selection["input_manifest_sha256"], "selection_sha256": "sha256:" + hashlib.sha256(selection_path.read_bytes()).hexdigest(), "processed_visit_count": len(files), "eligible_visit_count": 128, "observation_count": len(observations), "span_observation_count": len(span_observations), "runtime_seconds": time.monotonic() - start_time, "observations": observations, "span_observations": span_observations, "accounting": accounting}
    (output / "frame-observations.json").write_text(json.dumps(body, indent=2) + "\n")
    with (output / "probe-summary.csv").open("w", newline="") as stream:
        fields = ["visit_index", "split", "target_index", "receiver_id", "probe_index", "fractional_margin", "slope_frames", "ordinary_frames", "ordinary_updates", "modulo_v1_supported", "modulo_v2_supported"]
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in observations:
            writer.writerow({"visit_index": row["visit_index"], "split": row["split"], "target_index": row["target_index"], "receiver_id": row["receiver_id"], "probe_index": row["probe_index"], "fractional_margin": row["fractional_margin"], "slope_frames": row["slope"]["frame_count"], "ordinary_frames": row["ordinary_2pi"]["frame_count"], "ordinary_updates": row["ordinary_2pi"]["phase_update_count"], "modulo_v1_supported": row["modulo_pi_v1"]["supported_frame_count"], "modulo_v2_supported": row["modulo_pi_v2"]["supported_frame_count"]})


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--cache", type=Path, required=True); p.add_argument("--dense", type=Path, required=True); p.add_argument("--selection", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--limit", type=int)
    a = p.parse_args(); run(a.cache, a.dense, a.selection, a.output, a.limit)
