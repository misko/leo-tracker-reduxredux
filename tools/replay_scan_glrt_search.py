#!/usr/bin/env python3
"""Bounded GLRT search-resolution and known frequency-increment experiments."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from replay_scan_glrt_hyperparameters import select_tracks, support_center

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.fractional_epoch import fractional_log_peak
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score, refine_glrt64_epoch
from leo.storage.persistent_hop import PersistentHopIqStore, PersistentHopStoredCi16Reader

FFT_SIZES = (512, 1024, 2048, 4096, 8192)
SHIFTS_HZ = (-301.0, -137.0, 137.0, 301.0)
ALIAS_HZ = 1 / 4.4e-6


def alias_difference(value):
    return float(value - np.rint(value / ALIAS_HZ) * ALIAS_HZ)


def frequency_shift(iq, fs, shift_hz):
    return iq * np.exp(2j * np.pi * shift_hz * np.arange(len(iq)) / fs)


def dense_timing(score_at, step):
    """Search the same ±2-sample extent, then fit a local log parabola."""
    grid = tuple(float(x) for x in np.linspace(-2, 2, round(4 / step) + 1))
    scores = tuple(score_at(x) for x in grid)
    offset, _ = fractional_log_peak(tuple(s.exact_score for s in scores), grid)
    if offset is None:
        return None, None
    return offset, score_at(offset)


def acquisition_profiles(fs):
    baseline = SymbolwiseAcquisitionConfig(
        maximum_probe_samples=fs // 50,
        candidate_epoch_separation_samples=5,
        candidate_cfo_separation_hz=10000,
    )
    return {"baseline": baseline} | {
        name: replace(baseline, **changes)
        for name, changes in (
            ("coarse_40k", {"coarse_cfo_step_hz": 40000}),
            ("coarse_160k", {"coarse_cfo_step_hz": 160000}),
            ("fine_250", {"fine_cfo_step_hz": 250}),
            ("fine_1000", {"fine_cfo_step_hz": 1000}),
            ("conditioned_50", {"conditioned_cfo_step_hz": 50}),
            ("conditioned_200", {"conditioned_cfo_step_hz": 200}),
            ("radius_1000", {"conditioned_cfo_radius_hz": 1000}),
            ("radius_4000", {"conditioned_cfo_radius_hz": 4000}),
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("glrt", "acquisition"), default="glrt")
    args = parser.parse_args()
    selected = select_tracks(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    plan = {
        "source": str(args.source.resolve()),
        "mode": args.mode,
        "window_ms": 20,
        "fft_sizes": FFT_SIZES,
        "timing_extent_native_samples": [-2, 2],
        "timing_steps_native_samples": [0.5, 0.25, 0.125],
        "frequency_increments_hz": SHIFTS_HZ,
        "shift_probes_per_scan": 6,
        "acquisition_probes_per_scan": 4,
        "scans": [s["session_id"] for s in selected],
        "shift_policy": "Rotate recorded IQ; keep acquisition CFO and original timing fixed.",
        "limits": "Frozen selected tracks; shift error tests relative response, not absolute bias.",
    }
    plan_path = args.output / f"{args.mode}-plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != json.loads(json.dumps(plan)):
        raise ValueError("output plan differs; use a separate directory")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    store = PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    for selection in selected:
        sid = selection["session_id"]
        dest = args.output / args.mode / f"{sid}.json"
        if dest.exists():
            print(f"cached {sid}", flush=True)
            continue
        before_scan = time.monotonic()
        capture = store.inspect(sid)
        reader = PersistentHopStoredCi16Reader(store, capture)
        fs = selection["sample_rate_hz"]
        track = selection["track"]
        starts, cursor = {}, 0
        for visit in capture.manifest.receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        observations = track["observations"]
        shift_indexes = set(np.linspace(0, len(observations) - 1, 6).round().astype(int))
        acquisition_indexes = set(np.linspace(0, len(observations) - 1, 4).round().astype(int))
        rows, injections = [], []
        for index, obs in enumerate(observations):
            if args.mode == "acquisition" and index not in acquisition_indexes:
                continue
            original = obs["persisted"]
            raw = reader.read_valid_ci16(starts[obs["visit_index"]], fs // 50)
            column = reader.receiver_ids.index(obs["receiver_id"])
            iq = raw[:, column, 0].astype(float) + 1j * raw[:, column, 1].astype(float)
            epoch = original["integer_epoch_sample"]
            acquired = original["acquired_cfo_hz"]
            fraction = original["fractional_epoch_offset_samples"]
            meta = {"index": index, "candidate_id": obs["candidate_id"]}

            def record(
                profile,
                offset,
                score,
                elapsed,
                *,
                meta=meta,
                obs=obs,
                fs=fs,
                epoch=epoch,
                original=original,
                track=track,
                index=index,
            ):
                row = dict(meta, profile=profile, runtime_s=elapsed)
                if offset is None:
                    return row | {"status": "unbracketed"}
                delta = alias_difference(score.tracking_cfo_hz - obs["measured_cfo_hz"])
                center = support_center(fs, epoch, offset, 20)
                return row | {
                    "status": "complete",
                    "fraction_samples": offset,
                    "t_s": (original["integer_session_sample"] - epoch + center) / fs,
                    "y_hz": track["y_hz"][index] + delta * 11.2e9 / track["actual_rf_hz"],
                    "delta_to_original_hz": delta,
                    "exact_score": score.exact_score,
                    "margin": score.margin,
                    "tracking_cfo_hz": score.tracking_cfo_hz,
                }

            if args.mode == "acquisition":
                calibration = ReceiverFrequencyCalibration(str(obs["receiver_id"]), 0, "0" * 64)
                for name, config in acquisition_profiles(fs).items():
                    before = time.perf_counter()
                    found = acquire_symbolwise(
                        iq, fs, calibration, edge=track["edge"], config=config
                    )
                    acquisition_time = time.perf_counter() - before
                    candidates = []
                    for c in found.candidates:
                        refined = refine_glrt64_epoch(
                            iq,
                            fs,
                            integer_epoch_sample=c.refined_epoch_sample,
                            acquired_cfo_hz=c.absolute_cfo_hz,
                            edge=track["edge"],
                        )
                        period = round(fs / 750)
                        dist = abs(c.refined_epoch_sample - epoch)
                        candidates.append(
                            asdict(c)
                            | {
                                "epoch_distance_to_original_samples": min(dist, period - dist),
                                "fractional_status": refined.status.value,
                                "fractional_cfo_hz": refined.fractional_tracking_cfo_hz,
                                "fractional_margin": refined.fractional_margin,
                                "fractional_exact_score": refined.fractional_exact_score,
                            }
                        )
                    rows.append(
                        meta
                        | {
                            "profile": name,
                            "config": asdict(config),
                            "acquisition_runtime_s": acquisition_time,
                            "runtime_s": time.perf_counter() - before,
                            "original_cfo_hz": obs["measured_cfo_hz"],
                            "original_rank": original.get("candidate_rank"),
                            "candidates": candidates,
                        }
                    )
                continue

            for nfft in FFT_SIZES:
                before = time.perf_counter()
                score = conditioned_glrt64_score(
                    iq,
                    fs,
                    epoch_sample=epoch,
                    acquired_cfo_hz=acquired,
                    edge=track["edge"],
                    glrt_size=nfft,
                    fractional_epoch_offset_samples=fraction,
                )
                elapsed = time.perf_counter() - before
                if nfft == 512 and (
                    abs(score.tracking_cfo_hz - obs["measured_cfo_hz"]) > 1e-5
                    or abs(score.margin - obs["margin"]) > 1e-8
                ):
                    raise ValueError("baseline scorer disagrees with persisted observation")
                rows.append(record(f"fft_{nfft}", fraction, score, elapsed))
                if index in shift_indexes:
                    for shift in SHIFTS_HZ:
                        shifted = conditioned_glrt64_score(
                            frequency_shift(iq, fs, shift),
                            fs,
                            epoch_sample=epoch,
                            acquired_cfo_hz=acquired,
                            edge=track["edge"],
                            glrt_size=nfft,
                            fractional_epoch_offset_samples=fraction,
                        )
                        injections.append(
                            meta
                            | {
                                "fft_size": nfft,
                                "imposed_shift_hz": shift,
                                "observed_shift_hz": alias_difference(
                                    shifted.tracking_cfo_hz - score.tracking_cfo_hz
                                ),
                                "error_hz": alias_difference(
                                    shifted.tracking_cfo_hz - score.tracking_cfo_hz - shift
                                ),
                                "shifted_margin": shifted.margin,
                            }
                        )
            for step in (0.5, 0.25, 0.125):
                before = time.perf_counter()

                def score_at(offset, *, iq=iq, fs=fs, epoch=epoch, acquired=acquired, track=track):
                    return conditioned_glrt64_score(
                        iq,
                        fs,
                        epoch_sample=epoch,
                        acquired_cfo_hz=acquired,
                        edge=track["edge"],
                        glrt_size=512,
                        fractional_epoch_offset_samples=offset,
                    )

                offset, score = dense_timing(score_at, step)
                rows.append(record(f"timing_{step}", offset, score, time.perf_counter() - before))
        document = {
            "session_id": sid,
            "sample_rate_hz": fs,
            "tracklet_id": track["tracklet_id"],
            "manifest_sha256": capture.manifest_sha256,
            "rows": rows,
            "injections": injections,
        }
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
        print(
            f"{args.mode} {sid}: {len(rows)} rows, {time.monotonic() - before_scan:.1f}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
