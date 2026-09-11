#!/usr/bin/env python3
"""Bounded stored-IQ comparison of grid, continuous and joint GLRT estimators."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from evaluate_scan_glrt_rms import write_json
from replay_historic_glrt_joint import configurations
from replay_scan_glrt_search import frequency_shift
from review_scan_sample_rates import choose, delay_signal, half_rate

from leo.analysis.starlink.acquisition import ReceiverFrequencyCalibration, acquire_symbolwise
from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score, joint_refine
from leo.analysis.starlink.pilot_methods import refine_glrt64_epochs
from leo.storage.persistent_hop import PersistentHopIqStore, PersistentHopStoredCi16Reader

PROFILES = ["grid512", "grid8192", "local512", "joint512"]


def make_plan(root):
    paired_path = root / "reports/2026_09_11_sample_rate_review/plan.json"
    old_path = root / "reports/2026_09_10_historic_glrt_joint/plan.json"
    selection = json.loads(paired_path.read_text())["selection"]
    for scan in json.loads(old_path.read_text())["selection"]:
        if scan["sample_rate_hz"] != 2500000:
            continue
        evidence = json.loads(Path(scan["source_evidence"]).read_text())
        lane = next(s for s in evidence["series"] if s["tracklet_id"] == scan["tracklet_id"])
        probes = []
        for index in np.linspace(0, scan["probes"] - 1, 6).round().astype(int):
            obs = lane["observations"][index]
            seed = int(
                hashlib.sha256(("rates-20260911:" + obs["candidate_id"]).encode()).hexdigest()[:16],
                16,
            )
            rng = np.random.default_rng(seed)
            probes.append(
                {
                    "index": int(index),
                    "candidate_id": obs["candidate_id"],
                    "delays_ns": (-300 + (np.arange(4) + rng.random(4)) * 150).tolist(),
                    "shifts_hz": (-2000 + (np.arange(4) + rng.random(4)) * 1000).tolist(),
                }
            )
        selection.append({**scan, "selected_probes": probes})
    return {
        "selection": selection,
        "profiles": PROFILES,
        "fine_step_hz": 500,
        "conditioned_step_hz": 100,
        "window_ms": 20,
        "source_read_ms": 21,
        "crop_start_ms": 0.5,
        "association_radius_ns": 800,
        "frequency_tolerance_hz": 0.25,
        "refined_peaks": 3,
        "joint_timing_steps_ns": [200, 100],
        "joint_timing_radius_ns": 800,
        "joint_cfo_step_limit_hz": 2000,
        "source_plan_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [paired_path, old_path]
        },
        "policy": (
            "Same acquisition candidates across profiles. Local-only retains grid512 timing. "
            "Joint starts there and accepts nondecreasing exact score. Select highest exact "
            "score with margin >=0.025 within 800 ns of original integer phase; no truth CFO "
            "or shift used. Retain every candidate and every failure."
        ),
        "limits": (
            "Native recordings are different observations. Filtered 2.5 and native 5 share IQ "
            "but differ in bandwidth. Injected shifts measure relative consistency, "
            "not absolute accuracy. No new RF."
        ),
    }


def candidate_document(c, r, fs):
    return {
        "rank": c.rank,
        "integer_epoch_s": c.refined_epoch_sample / fs,
        "epoch_s": (c.refined_epoch_sample + r.fractional_epoch_offset_samples) / fs
        if r.fractional_epoch_offset_samples is not None
        else None,
        "fraction_samples": r.fractional_epoch_offset_samples,
        "acquired_cfo_hz": c.absolute_cfo_hz,
        "cfo_hz": r.fractional_tracking_cfo_hz,
        "margin": r.fractional_margin,
        "exact_score": r.fractional_exact_score,
        "status": r.status.value,
    }


def score_profiles(iq, fs, edge, acquisition):
    result = {}
    for grid in [512, 8192]:
        started = time.perf_counter()
        refined = refine_glrt64_epochs(
            iq,
            fs,
            integer_epoch_samples=[c.refined_epoch_sample for c in acquisition.candidates],
            acquired_cfo_hz=[c.absolute_cfo_hz for c in acquisition.candidates],
            edge=edge,
            glrt_size=grid,
        )
        result[f"grid{grid}"] = {
            "candidates": [
                candidate_document(c, r, fs)
                for c, r in zip(acquisition.candidates, refined, strict=True)
            ],
            "scoring_s": time.perf_counter() - started,
        }
    local, joint = [], []
    local_time = joint_time = 0.0
    for c, base in zip(acquisition.candidates, result["grid512"]["candidates"], strict=True):
        if base["fraction_samples"] is None:
            local.append(dict(base))
            joint.append(dict(base))
            continue
        started = time.perf_counter()
        score, diagnostics = continuous_glrt_score(
            iq,
            fs,
            anchor=c.refined_epoch_sample,
            offset=base["fraction_samples"],
            conditioning_cfo_hz=c.absolute_cfo_hz,
            edge=edge,
        )
        local_time += time.perf_counter() - started
        doc = {
            **base,
            "cfo_hz": score.tracking_cfo_hz,
            "exact_score": score.exact_score,
            "margin": score.margin,
            "diagnostics": diagnostics,
        }
        local.append(doc)
        started = time.perf_counter()
        offset, score, diagnostics = joint_refine(
            iq,
            fs,
            anchor=c.refined_epoch_sample,
            offset=base["fraction_samples"],
            conditioning_cfo_hz=c.absolute_cfo_hz,
            edge=edge,
            initial_score=score,
        )
        joint_time += time.perf_counter() - started
        joint.append(
            {
                **doc,
                "fraction_samples": offset,
                "epoch_s": (c.refined_epoch_sample + offset) / fs,
                "cfo_hz": score.tracking_cfo_hz,
                "exact_score": score.exact_score,
                "margin": score.margin,
                "diagnostics": diagnostics,
            }
        )
    result["local512"] = {
        "candidates": local,
        "scoring_s": result["grid512"]["scoring_s"] + local_time,
    }
    result["joint512"] = {
        "candidates": joint,
        "scoring_s": result["local512"]["scoring_s"] + joint_time,
    }
    return result


def replay(args, plan):
    started = time.monotonic()
    store = PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    completed = 0
    for scan in plan["selection"]:
        path = Path(scan["source_evidence"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != scan["evidence_sha256"]:
            raise ValueError("source evidence changed")
        evidence = json.loads(path.read_text())
        lane = next(s for s in evidence["series"] if s["tracklet_id"] == scan["tracklet_id"])
        capture = store.inspect(scan["session_id"])
        reader = PersistentHopStoredCi16Reader(store, capture)
        starts, cursor = {}, 0
        for visit in capture.manifest.receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        for probe in scan["selected_probes"]:
            destination = args.output / "raw" / f"{scan['session_id']}-{probe['index']:03d}.json"
            if destination.exists():
                continue
            obs = lane["observations"][probe["index"]]
            if obs["candidate_id"] != probe["candidate_id"] or obs["probe_index"] != 0:
                raise ValueError("probe binding changed")
            source_fs = scan["sample_rate_hz"]
            raw = reader.read_valid_ci16(starts[obs["visit_index"]], round(source_fs * 0.021))
            col = reader.receiver_ids.index(obs["receiver_id"])
            native = raw[:, col, 0].astype(float) + 1j * raw[:, col, 1].astype(float)
            versions = [(source_fs, "native", native)]
            if source_fs == 5000000:
                versions.append((2500000, "filtered", half_rate(native)))
            reference = (obs["persisted"]["integer_epoch_sample"] / source_fs - 0.0005) % (1 / 750)
            rows = []
            for fs, version, values in versions:
                calibration = ReceiverFrequencyCalibration(str(obs["receiver_id"]), 0, "0" * 64)
                cases = (
                    [("baseline", 0.0)]
                    + [("delay_ns", d) for d in probe["delays_ns"]]
                    + [("shift_hz", f) for f in probe["shifts_hz"]]
                )
                for kind, amount in cases:
                    if time.monotonic() - started > args.max_seconds:
                        raise TimeoutError("bounded replay exhausted allowance")
                    transformed = (
                        delay_signal(values, fs, amount * 1e-9)
                        if kind == "delay_ns"
                        else frequency_shift(values, fs, amount)
                        if kind == "shift_hz"
                        else values
                    )
                    crop = round(fs * 0.0005)
                    iq = transformed[crop : crop + fs // 50]
                    before = time.perf_counter()
                    acquisition = acquire_symbolwise(
                        iq,
                        fs,
                        calibration,
                        edge=lane["edge"],
                        config=configurations(fs)["fine500_conditioned100"],
                    )
                    acquisition_s = time.perf_counter() - before
                    profiles = score_profiles(iq, fs, lane["edge"], acquisition)
                    for profile, scored in profiles.items():
                        rows.append(
                            {
                                "candidate_id": probe["candidate_id"],
                                "index": probe["index"],
                                "fs": fs,
                                "version": version,
                                "profile": profile,
                                "case": kind,
                                "amount": amount,
                                "reference_epoch_s": reference,
                                "target": choose(scored["candidates"], reference),
                                "acquisition_s": acquisition_s,
                                **scored,
                            }
                        )
            write_json(
                destination,
                {
                    "session_id": scan["session_id"],
                    "manifest_sha256": capture.manifest_sha256,
                    "rows": rows,
                },
            )
            completed += 1
            print(
                f"{scan['session_id']} probe {probe['index']} complete; "
                f"{time.monotonic() - started:.1f}s",
                flush=True,
            )
            if args.max_probes and completed >= args.max_probes:
                return
    print(f"Replay complete in {time.monotonic() - started:.1f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=1200)
    parser.add_argument("--max-probes", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "plan.json"
    plan = (
        json.loads(path.read_text())
        if path.exists()
        else make_plan(Path(__file__).resolve().parents[1])
    )
    if not path.exists():
        write_json(path, plan)
    if not args.plan_only:
        replay(args, plan)


if __name__ == "__main__":
    main()
