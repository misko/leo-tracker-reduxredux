#!/usr/bin/env python3
"""Bounded historical acquisition/GLRT factorial with fully reacquired shifts."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from evaluate_scan_glrt_rms import write_json
from replay_scan_glrt_hyperparameters import support_center
from replay_scan_glrt_search import frequency_shift

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import refine_glrt64_epochs
from leo.storage.persistent_hop import PersistentHopIqStore, PersistentHopStoredCi16Reader


def configurations(fs):
    return {
        f"fine{fine}_conditioned{conditioned}": SymbolwiseAcquisitionConfig(
            maximum_probe_samples=fs // 50,
            fine_cfo_step_hz=fine,
            conditioned_cfo_step_hz=conditioned,
            candidate_epoch_separation_samples=5,
            candidate_cfo_separation_hz=10000,
        )
        for fine in (500, 250)
        for conditioned in (100, 50)
    }


def stratified_shifts(candidate_id):
    seed = int(
        hashlib.sha256(("historic-glrt-20260910:" + candidate_id).encode()).hexdigest()[:16], 16
    )
    rng = np.random.default_rng(seed)
    return (-2000 + (np.arange(8) + rng.random(8)) * 500).tolist()


def select_candidate(candidates, epoch=None, period=None):
    """Rank by GLRT evidence only; no CFO reference or imposed shift is used."""
    eligible = [c for c in candidates if c["cfo_hz"] is not None and c["margin"] >= 0.025]
    if epoch is not None:
        eligible = [
            c
            for c in eligible
            if abs((c["epoch_sample"] - epoch + period / 2) % period - period / 2) <= 2
        ]
    return max(eligible, key=lambda c: (c["exact_score"], -c["rank"])) if eligible else None


def make_plan(source, previous):
    used = set(json.loads((previous / "glrt-plan.json").read_text())["scans"])
    used.update(
        r["session_id"]
        for r in json.loads((source / "orbit-summary.json").read_text())["figure_hypotheses"]
    )
    docs = [(p, json.loads(p.read_text())) for p in (source / "evidence").glob("scan*.json")]
    chosen = []
    for fs in (2500000, 5000000):
        pool = sorted(
            [
                (p, d)
                for p, d in docs
                if d["inventory"]["sample_rate_hz"] == fs
                and d["inventory"]["session_id"] not in used
                and d["series"]
                and max(np.ptp(s["t_s"]) for s in d["series"]) >= 30
            ],
            key=lambda item: item[1]["inventory"]["reference_utc_ns"],
        )
        for i in np.linspace(0, len(pool) - 1, 3).round().astype(int):
            path, doc = pool[i]
            lane = max(doc["series"], key=lambda s: np.ptp(s["t_s"]))
            shift_indexes = [len(lane["observations"]) // 3, 2 * len(lane["observations"]) // 3]
            chosen.append(
                {
                    "session_id": doc["inventory"]["session_id"],
                    "sample_rate_hz": fs,
                    "source_evidence": str(path.resolve()),
                    "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "tracklet_id": lane["tracklet_id"],
                    "probes": len(lane["observations"]),
                    "span_s": float(np.ptp(lane["t_s"])),
                    "shifts": {
                        str(index): stratified_shifts(lane["observations"][index]["candidate_id"])
                        for index in shift_indexes
                    },
                }
            )
    return {
        "source_report": str(source.resolve()),
        "selection": chosen,
        "selection_rule": (
            "Three evenly time-spaced scans per rate not used in earlier raw replay, "
            "longest primary lane >=30 s, all its probes."
        ),
        "window_ms": 20,
        "glrt_grids": [512, 8192],
        "acquisition_configurations": {
            str(fs): {name: asdict(c) for name, c in configurations(fs).items()}
            for fs in (2500000, 5000000)
        },
        "selection_policy": (
            "Passing candidate with maximum exact GLRT score within two integer samples "
            "of original target phase; no frequency gate. Also retain global GLRT winner."
        ),
        "shift_policy": (
            "Eight stratified offsets across [-2000,2000) Hz per selected probe; "
            "raw IQ rotated before independent acquisition. "
            "All parameters and shifts frozen before replay."
        ),
        "limitations": (
            "Tracks and epoch association are baseline-selected; new raw replay does not "
            "constitute untouched end-to-end validation. "
            "Shift error is relative, not absolute truth."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=900)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    proposed = json.loads(json.dumps(make_plan(args.source, args.previous)))
    path = args.output / "plan.json"
    if path.exists() and json.loads(path.read_text()) != proposed:
        raise ValueError("saved plan differs; use a new output directory")
    write_json(path, proposed)
    if args.plan_only:
        print(
            f"Frozen {len(proposed['selection'])} scans / "
            f"{sum(s['probes'] for s in proposed['selection'])} probes",
            flush=True,
        )
        return
    before_run = time.monotonic()
    store = PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    for selection in proposed["selection"]:
        dest = args.output / "raw" / f"{selection['session_id']}.json"
        if dest.exists():
            print(f"cached {selection['session_id']}", flush=True)
            continue
        evidence_path = Path(selection["source_evidence"])
        if hashlib.sha256(evidence_path.read_bytes()).hexdigest() != selection["evidence_sha256"]:
            raise ValueError("source evidence changed")
        evidence = json.loads(evidence_path.read_text())
        lane = next(s for s in evidence["series"] if s["tracklet_id"] == selection["tracklet_id"])
        fs = selection["sample_rate_hz"]
        capture = store.inspect(selection["session_id"])
        reader = PersistentHopStoredCi16Reader(store, capture)
        starts, cursor = {}, 0
        for visit in capture.manifest.receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        rows = []
        before_scan = time.monotonic()
        for index, obs in enumerate(lane["observations"]):
            if time.monotonic() - before_run > args.max_seconds:
                raise TimeoutError("bounded historical replay exhausted its wall-time allowance")
            original = obs["persisted"]
            if obs["probe_index"] != 0:
                raise ValueError("expected one source probe at visit start")
            raw = reader.read_valid_ci16(starts[obs["visit_index"]], fs // 50)
            col = reader.receiver_ids.index(obs["receiver_id"])
            iq = raw[:, col, 0].astype(float) + 1j * raw[:, col, 1].astype(float)
            offsets = [0.0] + selection["shifts"].get(str(index), [])
            calibration = ReceiverFrequencyCalibration(str(obs["receiver_id"]), 0.0, "0" * 64)
            for offset in offsets:
                values = iq if offset == 0 else frequency_shift(iq, fs, offset)
                for name, config in configurations(fs).items():
                    before = time.perf_counter()
                    acquired = acquire_symbolwise(
                        values, fs, calibration, edge=lane["edge"], config=config
                    )
                    acquisition_seconds = time.perf_counter() - before
                    for grid in (512, 8192):
                        before = time.perf_counter()
                        refined = refine_glrt64_epochs(
                            values,
                            fs,
                            integer_epoch_samples=[
                                c.refined_epoch_sample for c in acquired.candidates
                            ],
                            acquired_cfo_hz=[c.absolute_cfo_hz for c in acquired.candidates],
                            edge=lane["edge"],
                            glrt_size=grid,
                        )
                        scoring_seconds = time.perf_counter() - before
                        candidates = []
                        for c, r in zip(acquired.candidates, refined, strict=True):
                            row = {
                                "rank": c.rank,
                                "epoch_sample": c.refined_epoch_sample,
                                "acquired_cfo_hz": c.absolute_cfo_hz,
                                "status": r.status.value,
                                "fraction_samples": r.fractional_epoch_offset_samples,
                                "cfo_hz": r.fractional_tracking_cfo_hz,
                                "margin": r.fractional_margin,
                                "exact_score": r.fractional_exact_score,
                            }
                            if r.fractional_epoch_offset_samples is not None:
                                row["t_s"] = (
                                    original["integer_session_sample"]
                                    - original["integer_epoch_sample"]
                                    + support_center(
                                        fs,
                                        c.refined_epoch_sample,
                                        r.fractional_epoch_offset_samples,
                                        20,
                                    )
                                ) / fs
                            candidates.append(row)
                        rows.append(
                            {
                                "index": index,
                                "candidate_id": obs["candidate_id"],
                                "visit_index": obs["visit_index"],
                                "imposed_shift_hz": offset,
                                "profile": f"{name}_fft{grid}",
                                "acquisition_profile": name,
                                "grid_points": grid,
                                "acquisition_s": acquisition_seconds,
                                "scoring_s": scoring_seconds,
                                "candidates": candidates,
                                "target": select_candidate(
                                    candidates, original["integer_epoch_sample"], round(fs / 750)
                                ),
                                "global_winner": select_candidate(candidates),
                                "original_cfo_hz": obs["measured_cfo_hz"],
                                "original_t_s": (
                                    original["integer_session_sample"]
                                    - original["integer_epoch_sample"]
                                    + support_center(
                                        fs,
                                        original["integer_epoch_sample"],
                                        original["fractional_epoch_offset_samples"],
                                        20,
                                    )
                                )
                                / fs,
                                "original_branch_hz": lane["y_hz"][index],
                            }
                        )
            if index % 10 == 0:
                print(
                    f"{selection['session_id']} probe {index + 1}/{selection['probes']} "
                    f"({time.monotonic() - before_run:.1f}s)",
                    flush=True,
                )
        write_json(
            dest,
            {
                **selection,
                "actual_rf_hz": lane["actual_rf_hz"],
                "rows": rows,
                "manifest_sha256": capture.manifest_sha256,
                "runtime_s": time.monotonic() - before_scan,
            },
        )
        print(f"completed {selection['session_id']}: {len(rows)} profile observations", flush=True)


if __name__ == "__main__":
    main()
