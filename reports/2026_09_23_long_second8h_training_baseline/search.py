#!/usr/bin/env python3
"""Parallel blind tau-zero baseline on the second frozen TRAIN group."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path

import numpy as np

LEVELS_KM = (100.0, 50.0, 25.0, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, 0.1953125)
COUNTS = (1, 6, 16, 79)
_SINGLE = None
_SESSIONS = None


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def combined_score(single, sessions, latitude, longitude, include_evaluation=False):
    weighted_loss = total_weight = 0.0
    rows = []
    for session in sessions:
        objective, tracks = single.score_point(
            session["prepared"], session["candidate_ids"], latitude, longitude, include_evaluation
        )
        weighted_loss += session["weight"] * objective**2
        total_weight += session["weight"]
        rows.append(
            {
                "session_id": session["session_id"],
                "training_objective_rmse_hz": objective,
                "tracks": tracks,
            }
        )
    return float(np.sqrt(weighted_loss / total_weight)), rows


def worker(task):
    count, prior_name = task
    active = _SESSIONS[:count]

    def evaluate(latitude, longitude, held=False):
        return combined_score(_SINGLE, active, latitude, longitude, held)

    started = time.monotonic()
    search = _SINGLE.search_prior(prior_name, _SINGLE.PRIORS[prior_name], evaluate)
    coarse = [row for row in search["trace"] if row["level_km"] >= 1.5625]
    search["coarse_control_selected"] = min(coarse, key=lambda row: row["objective_rmse_hz"])
    return {
        "scan_count": count,
        "prior": prior_name,
        "runtime_s": time.monotonic() - started,
        "search": search,
    }


def run(args):
    global _SINGLE, _SESSIONS
    if args.output.exists():
        raise FileExistsError("fresh output required")
    manifest = json.loads(args.manifest.read_text())
    sessions = manifest["source_group"]["session_ids"]
    if (
        len(sessions) != 79
        or manifest["source_group"]["utc_8h_start"] != "2026-09-21T16:00:00+00:00"
    ):
        raise ValueError("expected frozen Sep21 16Z 79-scan TRAIN group")
    if not all(manifest["partition_checks"].values()):
        raise ValueError("manifest partition exclusion checks failed")
    _SINGLE = load_module(args.single_tool, "second8h_single")
    _SINGLE.LEVELS_KM = LEVELS_KM
    loader = load_module(args.fast_loader, "second8h_loader")
    bindings = []
    prepared_started = time.monotonic()
    loaded = []
    for session_id in sessions:
        directory = args.cache_root / session_id
        row = loader.load_session(_SINGLE, directory, session_id)
        loaded.append(row)
        bindings.append(
            {
                "session_id": session_id,
                "receipt": digest(row["receipt"]),
                "cache": digest(row["cache"]),
            }
        )
    _SESSIONS = loaded
    preparation_s = time.monotonic() - prepared_started
    tasks = [(count, prior) for count in COUNTS for prior in _SINGLE.PRIORS]
    started = time.monotonic()
    context = multiprocessing.get_context("fork")
    with concurrent.futures.ProcessPoolExecutor(max_workers=4, mp_context=context) as pool:
        completed = list(pool.map(worker, tasks))
    if len(completed) != 8:
        raise RuntimeError("parallel search returned incomplete arm set")
    completed.sort(key=lambda row: (row["scan_count"], row["prior"]))
    inference = {
        "schema": "second8h-nested-blind-tau0-position/v1",
        "position_truth_used": False,
        "reserved_rows_used": False,
        "session_ids": sessions,
        "levels_km": LEVELS_KM,
        "beam_width": _SINGLE.BEAM,
        "preparation_s": preparation_s,
        "runtime_s": time.monotonic() - started,
        "arms": completed,
        "bindings": {
            "manifest": digest(args.manifest),
            "single_tool": digest(args.single_tool),
            "fast_loader": digest(args.fast_loader),
            "tool": digest(Path(__file__)),
            "sessions": bindings,
        },
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    for arm in results["arms"]:
        active = loaded[: arm["scan_count"]]
        point = arm["search"]["selected"]
        _, scans = combined_score(
            _SINGLE, active, point["latitude_deg"], point["longitude_deg"], True
        )
        capped = uncapped = total = 0.0
        for scan, source in zip(scans, active, strict=True):
            for track, evidence in zip(scan["tracks"], source["prepared"], strict=True):
                weight, value = evidence["weight_s"], track.get("evaluation_rms_hz", 800.0)
                capped += weight * min(800.0, value) ** 2
                uncapped += weight * value**2
                total += weight
        point["scans"] = scans
        point["reserved_capped800_rmse_hz"] = float(np.sqrt(capped / total))
        point["reserved_uncapped_rmse_hz"] = float(np.sqrt(uncapped / total))
        point["reference_error_km"] = _SINGLE.haversine_km(
            (point["latitude_deg"], point["longitude_deg"]), _SINGLE.REFERENCE
        )
    results["reference_coordinate"] = {
        "latitude_deg": _SINGLE.REFERENCE[0],
        "longitude_deg": _SINGLE.REFERENCE[1],
        "role": "post-seal only",
    }
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--single-tool", type=Path, required=True)
    parser.add_argument("--fast-loader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")
    main()
