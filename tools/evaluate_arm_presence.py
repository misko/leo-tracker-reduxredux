#!/usr/bin/env python3
"""Bounded desktop replay of archived IQ; no RF, deployment, or production writes.

Run freeze, then develop, then heldout. The protocol is sealed before scoring;
heldout refuses to run before development thresholds have been saved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.research.arm_presence import (
    MARGIN_GATE,
    TimingSeed,
    best_candidate,
    cached_glrt,
    fresh_glrt,
    noise_control,
    periodicity_scout,
    pss_scout,
    reference_label,
)
from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.acquisition import _folded_anchor_score_grid_backend
from leo.contracts.starlink_frequency import starlink_edge_if_center_frequency_hz
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore

# Selected by completion, qualification, rate and chronology, before IQ scoring.
SESSIONS = (
    ("develop", "scan-hop-a5018b64a98f25e7", 5_000_000),
    ("develop", "scan-hop-0cff88ddaeec79f2", 2_500_000),
    ("heldout", "scan-hop-6762d7b8fced3bfc", 5_000_000),
    ("heldout", "scan-hop-bf8e9ccbb5952704", 2_500_000),
)


def timed(function, *args, **kwargs):
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    result = function(*args, **kwargs)
    return result, {
        "cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, document):
    with path.open("x") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")


def freeze(root, output, reuse_development=None):
    sources = PersistentHopAnalysisInputStore(PersistentHopIqStore.open_read_only(root))
    sessions = []
    for split, session_id, rate in SESSIONS:
        source = sources.source(session_id)
        if (
            source.sample_rate_hz != rate
            or source.plan.valid_visit_ms != 120
            or not source.receipt.qualified
        ):
            raise ValueError("archive differs from proposed protocol")
        sessions.append(
            {
                "split": split,
                "session_id": session_id,
                "rate_hz": rate,
                "input_uri": source.input_uri,
                "input_manifest_sha256": source.input_manifest_sha256,
                "visit_indexes": list(range(150 * 8, 158 * 8)),
            }
        )
    reuse = None
    if reuse_development is not None:
        previous = json.loads((reuse_development / "protocol.json").read_text())
        numerical_path = "src/leo/analysis/research/arm_presence.py"
        if previous["source_sha256"][numerical_path] != digest(Path(numerical_path)):
            raise ValueError("cannot reuse baselines from different numerical code")
        if previous["sessions"] != sessions:
            raise ValueError("cannot reuse different scan excerpts")
        reuse = {
            "directory": str(reuse_development.resolve()),
            "sha256": {
                name: digest(reuse_development / name)
                for name in (
                    "protocol.json",
                    "develop-visits.jsonl",
                    "develop-controls.jsonl",
                    "develop-execution.json",
                )
            },
        }
    write_new(
        output / "protocol.json",
        {
            "experiment": "arm-presence-desktop-screen-v2",
            "pss_projection": "existing standard edge-dependent half-bin reference",
            "reuse_development_baselines": reuse,
            "sessions": sessions,
            "reference_windows_ms": [0, 20, 40, 60, 80, 100],
            "reference_candidates": 8,
            "reduced_candidates": 2,
            "fractional_margin_gate": MARGIN_GATE,
            "cache_timing_radius_us": 2.4,
            "force_reacquire_every_revisits": 4,
            "synthetic_controls_per_rate_split": 32,
            "controls": "16 Gaussian + 16 tone/noise, each dual RX, 120 ms; not real RF truth",
            "scout_threshold": (
                "per rate, strictly above max development dual-RX synthetic-control score"
            ),
            "notes": [
                "All cached seeds originate in this detector's own earlier visits.",
                "Cache resets between scans; no TLE/site data or archive GLRT seeds.",
                "Missing full-visit reference hits are unresolved, never negative truth.",
                "One short contiguous excerpt per scan, not a full 300 s replay.",
            ],
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "source_sha256": {
                str(path): digest(path)
                for path in (Path(__file__), Path("src/leo/analysis/research/arm_presence.py"))
            },
        },
    )


def _score_blocks(function, blocks, rate, kwargs):
    return [function(block, rate, **kwargs) for block in blocks]


def _reference_windows(samples, rate, edge, starts):
    windows, timings = [], []
    for start in starts:
        result, timing = timed(
            fresh_glrt,
            samples[start * rate // 1000 : (start + 20) * rate // 1000],
            rate,
            edge=edge,
            candidate_count=8,
        )
        windows.append(result)
        timings.append(timing)
    return windows, timings


def scout_windows(values, rate, slice_offset):
    output = {}
    for name, offsets in (("first20", (0,)), ("spread60", (0, 50, 100)), ("full120", None)):
        blocks = (
            [values]
            if offsets is None
            else [
                values[round(offset * rate / 1000) : round((offset + 20) * rate / 1000)]
                for offset in offsets
            ]
        )
        for algorithm, function in (("lag", periodicity_scout), ("pss", pss_scout)):
            kwargs = {"slice_center_offset_hz": slice_offset} if algorithm == "pss" else {}
            result, timing = timed(_score_blocks, function, blocks, rate, kwargs)
            key = "pss_z" if algorithm == "pss" else "lag_margin"
            output[f"{algorithm}_{name}"] = {
                "score": max(item[key] for item in result),
                **timing,
                "window_scores": [item[key] for item in result],
            }
    return output


def run_controls(output, split, baseline):
    path = output / f"{split}-controls.jsonl"
    if path.exists():
        raise ValueError("control output exists; use a new experiment output directory")
    with path.open("x") as stream:
        for rate in (2_500_000, 5_000_000):
            for index in range(32):
                kind = "gaussian" if index < 16 else "tone_noise"
                receivers = []
                for rx in (0, 1):
                    seed = 90000 + (10000 if split == "heldout" else 0) + rate + index * 2 + rx
                    values = noise_control(round(rate * 0.120), rate, seed=seed, kind=kind)
                    offset = starlink_edge_if_center_frequency_hz(1, "lower") - (
                        starlink_pss_channel_reference_hz(1, "lower")
                    )
                    scouts = scout_windows(values, rate, offset)
                    prior = baseline.get((rate, index))
                    if prior is not None:
                        cold_result = prior["receivers"][rx]["cold2"]
                    else:
                        cold, timing = timed(
                            fresh_glrt, values[: rate // 50], rate, edge="lower", candidate_count=2
                        )
                        best = best_candidate(cold)
                        cold_result = {"margin": None if best is None else best.margin, **timing}
                    receivers.append(
                        {
                            "rx": rx,
                            "scouts": scouts,
                            "cold2": cold_result,
                        }
                    )
                stream.write(
                    json.dumps(
                        {"rate_hz": rate, "index": index, "kind": kind, "receivers": receivers},
                        allow_nan=False,
                    )
                    + "\n"
                )
                stream.flush()
            print(f"{split}: completed {rate} synthetic controls", flush=True)


def run_archive(root, output, split, protocol, baseline):
    sources = PersistentHopAnalysisInputStore(PersistentHopIqStore.open_read_only(root))
    with (output / f"{split}-visits.jsonl").open("x") as stream:
        for session in protocol["sessions"]:
            if session["split"] != split:
                continue
            source = sources.source(session["session_id"])
            if source.input_manifest_sha256 != session["input_manifest_sha256"]:
                raise ValueError("input manifest changed after freeze")
            rate = source.sample_rate_hz
            cache = {}
            for ordinal, index in enumerate(session["visit_indexes"]):
                visit, io = timed(source.read_visit, index)
                values, conversion = timed(visit.complex_samples)
                span = visit.span
                offset = span.actual_if_center_hz - starlink_pss_channel_reference_hz(
                    span.target.channel, span.target.edge
                )
                receivers = []
                for rx in (0, 1):
                    samples = values[:, rx]
                    scouts = scout_windows(samples, rate, offset)
                    prior = baseline.get((source.session_id, index))
                    if prior is not None:
                        receivers.append({**prior["receivers"][rx], "scouts": scouts})
                        continue
                    cold, cold_time = timed(
                        fresh_glrt,
                        samples[: rate // 50],
                        rate,
                        edge=span.target.edge,
                        candidate_count=2,
                    )
                    cold_best = best_candidate(cold)
                    key = (span.target_index, rx)
                    cached, cache_time = (), {"cpu_ms": 0.0, "wall_ms": 0.0}
                    seed = cache.get(key)
                    if seed is not None:
                        cached, cache_time = timed(
                            cached_glrt,
                            samples[: rate // 50],
                            rate,
                            edge=span.target.edge,
                            device_counter=span.valid_device_sample_counter,
                            seed=seed,
                        )
                    cached_best = best_candidate(cached)
                    forced = ordinal // 8 % 4 == 0
                    use_cold = forced or cached_best is None or not cached_best.passed
                    chosen = cold_best if use_cold else cached_best
                    if chosen is not None and chosen.passed:
                        cache[key] = TimingSeed(span.valid_device_sample_counter, rate, chosen)
                    else:
                        cache.pop(key, None)
                    # Dense reference is evaluated only AFTER the causal detector decision.
                    reference_result, reference_time = timed(
                        _reference_windows,
                        samples,
                        rate,
                        span.target.edge,
                        protocol["reference_windows_ms"],
                    )
                    reference, reference_window_times = reference_result
                    receivers.append(
                        {
                            "rx": rx,
                            "scouts": scouts,
                            "cold2": {
                                "candidate": None if cold_best is None else asdict(cold_best),
                                **cold_time,
                            },
                            "cached": {
                                "had_seed": seed is not None,
                                "candidate": None if cached_best is None else asdict(cached_best),
                                **cache_time,
                            },
                            "hybrid": {
                                "used_cold": use_cold,
                                "forced": forced,
                                "candidate": None if chosen is None else asdict(chosen),
                                "cpu_ms": cache_time["cpu_ms"]
                                + (cold_time["cpu_ms"] if use_cold else 0),
                                "wall_ms": cache_time["wall_ms"]
                                + (cold_time["wall_ms"] if use_cold else 0),
                            },
                            "reference": {
                                "label": reference_label(reference),
                                "windows": [[asdict(c) for c in window] for window in reference],
                                "window_times": reference_window_times,
                                **reference_time,
                            },
                        }
                    )
                stream.write(
                    json.dumps(
                        {
                            "session_id": source.session_id,
                            "rate_hz": rate,
                            "visit_index": index,
                            "target_index": span.target_index,
                            "channel": span.target.channel,
                            "edge": span.target.edge,
                            "device_counter": span.valid_device_sample_counter,
                            "slice_center_offset_hz": offset,
                            "read_and_decompress": io,
                            "ci16_to_complex": conversion,
                            "receivers": receivers,
                        },
                        allow_nan=False,
                    )
                    + "\n"
                )
                stream.flush()
                if (ordinal + 1) % 8 == 0:
                    print(f"{split}: {source.session_id} {ordinal + 1}/64 visits", flush=True)


def thresholds(output):
    rows = [
        json.loads(line) for line in (output / "develop-controls.jsonl").read_text().splitlines()
    ]
    selected = {}
    for rate in (2_500_000, 5_000_000):
        controls = [row for row in rows if row["rate_hz"] == rate]
        selected[str(rate)] = {
            name: float(
                np.nextafter(
                    max(rx["scouts"][name]["score"] for row in controls for rx in row["receivers"]),
                    np.inf,
                )
            )
            for name in controls[0]["receivers"][0]["scouts"]
        }
    write_new(
        output / "thresholds.json",
        {"thresholds": selected, "source_sha256": digest(output / "develop-controls.jsonl")},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "develop", "heldout"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-development", type=Path)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output == root or root in output.parents or Path("/mnt/qnap01") in (output, *output.parents):
        raise ValueError("research output must be outside archive/QNAP")
    output.mkdir(parents=True, exist_ok=True)
    if args.stage == "freeze":
        freeze(root, output, args.reuse_development)
        print("protocol frozen", flush=True)
        return
    protocol = json.loads((output / "protocol.json").read_text())
    for path, expected in protocol["source_sha256"].items():
        if digest(Path(path)) != expected:
            raise ValueError("experiment implementation changed after freeze")
    if args.stage == "heldout" and not (output / "thresholds.json").exists():
        raise ValueError("freeze development thresholds before opening heldout IQ")
    baseline_visits, baseline_controls = {}, {}
    reuse = protocol.get("reuse_development_baselines")
    if args.stage == "develop" and reuse is not None:
        directory = Path(reuse["directory"])
        for name, expected in reuse["sha256"].items():
            if digest(directory / name) != expected:
                raise ValueError("reused development baseline digest mismatch")
        baseline_visits = {
            (row["session_id"], row["visit_index"]): row
            for row in (
                json.loads(line)
                for line in (directory / "develop-visits.jsonl").read_text().splitlines()
            )
        }
        baseline_controls = {
            (row["rate_hz"], row["index"]): row
            for row in (
                json.loads(line)
                for line in (directory / "develop-controls.jsonl").read_text().splitlines()
            )
        }
    started = time.time()
    run_controls(output, args.stage, baseline_controls)
    run_archive(root, output, args.stage, protocol, baseline_visits)
    if args.stage == "develop":
        thresholds(output)
    write_new(
        output / f"{args.stage}-execution.json",
        {
            "elapsed_s": time.time() - started,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "acquisition_backend": _folded_anchor_score_grid_backend(),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "protocol_sha256": digest(output / "protocol.json"),
        },
    )


if __name__ == "__main__":
    main()
