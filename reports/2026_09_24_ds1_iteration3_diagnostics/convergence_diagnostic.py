#!/usr/bin/env python3
"""Fixed-winner, reference-free iteration-3 rate convergence diagnostic.

This predeclared check holds each published iteration-3 geographic/timing
winner and its all-qualified hard association procedure fixed.  It only raises
the L-BFGS-B iteration cap from the screening value of 30 to 120 and 300, so
the result distinguishes optimizer truncation from weakly identified rate
parameters without using a reference coordinate or changing selection.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITERATION3 = ROOT / "reports/2026_09_24_ds1_joint_rate_search/iteration3-results.json"
JOINT = ROOT / "reports/2026_09_24_ds1_joint_rate_search/joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
CAPS = (30, 120, 300)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty quantile input")
    return {
        label: float(
            ordered[0] if fraction == 0.0 else ordered[math.ceil(fraction * len(ordered)) - 1]
        )
        for label, fraction in (
            ("min", 0.0),
            ("p10", 0.1),
            ("median", 0.5),
            ("p90", 0.9),
            ("max", 1.0),
        )
    }


def task_from_result(item: dict[str, Any]) -> dict[str, Any]:
    source = json.loads(Path(item["source_global_time_artifact"]).read_text())
    if source.get("reference_used_for_fit") is not False or source.get("partition") != "train":
        raise ValueError("winner source must attest reference-free TRAIN inference")
    return {
        "task_id": "iteration3-convergence-" + str(source["task_id"]),
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def information_proxy(support: Any, joint: Any) -> dict[str, Any]:
    """Diagonal data curvature after per-track CFO profiling, at zero residual."""
    sources = np.unique(support.source.astype(str))
    tracks = np.unique(support.track.astype(str))
    feature = support.sensitivity_hz_s * support.age_h
    centered = np.zeros_like(feature, dtype=float)
    for track in tracks:
        mask = support.track.astype(str) == track
        centered[mask] = feature[mask] - np.mean(feature[mask])
    rows = []
    prior_curvature = 1.0 / joint.RATE_SIGMA_S_H**2
    for source in sources:
        mask = support.source.astype(str) == source
        data_curvature = float(np.sum(centered[mask] ** 2) / joint.ROBUST_SCALE_HZ**2)
        rows.append(
            {
                "candidate_id": str(source),
                "track_count": int(len(set(support.track.astype(str)[mask]))),
                "data_curvature": data_curvature,
                "data_fraction_of_local_curvature": data_curvature
                / (data_curvature + prior_curvature),
            }
        )
    fractions = [row["data_fraction_of_local_curvature"] for row in rows]
    curvatures = [row["data_curvature"] for row in rows]
    track_counts = [float(row["track_count"]) for row in rows]
    return {
        "definition": (
            "zero-residual diagonal curvature after per-track CFO profiling; a proxy, "
            "not a confidence interval"
        ),
        "source_count": len(rows),
        "data_curvature": quantiles(curvatures),
        "data_fraction_of_local_curvature": quantiles(fractions),
        "associated_tracks_per_source": quantiles(track_counts),
        "sources_with_data_fraction_below_0_5": sum(value < 0.5 for value in fractions),
        "sources_with_one_track": sum(value == 1.0 for value in track_counts),
    }


def rms_difference(left: dict[str, float], right: dict[str, float]) -> tuple[float, float]:
    keys = sorted(set(left) & set(right))
    values = [left[key] - right[key] for key in keys]
    return float(np.sqrt(np.mean(np.square(values)))), float(max(map(abs, values)))


def diagnose(item: dict[str, Any], joint: Any, existing: Any, orbit: Any) -> dict[str, Any]:
    winner = item["winner"]
    engine = existing.FullObservationEngine(existing.validate_task(task_from_result(item)))
    support = joint.hard_support(
        engine, orbit, winner["latitude_deg"], winner["longitude_deg"], winner["tau_s"]
    )
    fits = {}
    for cap in CAPS:
        joint.SCREENING_MAX_ITERATIONS = cap
        fits[str(cap)] = joint.fit_rate_support(support)
    base, long = fits["30"], fits["300"]
    rate_rms, rate_max = rms_difference(base["rate_corrections_s_h"], long["rate_corrections_s_h"])
    selected_counts = Counter(
        row["candidate_id"] for row in support.associations if row["candidate_id"] is not None
    )
    return {
        "task_id": item["task_id"],
        "fixed_winner": {
            key: winner[key]
            for key in ("latitude_deg", "longitude_deg", "tau_s", "east_km", "north_km")
        },
        "association": {
            "track_count": len(support.associations),
            "candidate_count": len(selected_counts),
            "tracks_per_candidate": quantiles([float(value) for value in selected_counts.values()]),
        },
        "identifiability_proxy": information_proxy(support, joint),
        "fits_by_iteration_cap": {
            cap: {
                key: fit[key]
                for key in (
                    "selection_objective",
                    "full_observation_capped_loss",
                    "prior_penalty",
                    "converged",
                    "iterations",
                    "rate_boundary_count",
                    "maximum_phase_s",
                )
            }
            for cap, fit in fits.items()
        },
        "cap_30_to_300": {
            "selection_objective_delta": long["selection_objective"] - base["selection_objective"],
            "capped_loss_delta": long["full_observation_capped_loss"]
            - base["full_observation_capped_loss"],
            "rate_rms_difference_s_h": rate_rms,
            "rate_maximum_absolute_difference_s_h": rate_max,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    document = json.loads(ITERATION3.read_text())
    if document.get("complete") is not True or document.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-3 input must attest complete reference-free inference")
    joint = load(JOINT, "iteration3_convergence_joint")
    existing = load(RUNNER, "iteration3_convergence_existing")
    orbit = load(ORBIT, "iteration3_convergence_orbit")
    rows = [diagnose(item, joint, existing, orbit) for item in document["results"]]
    payload = {
        "schema": "ds1-iteration3-fixed-winner-rate-convergence/v1",
        "complete": True,
        "reference_used_for_fit": False,
        "selection_changed": False,
        "predeclared_iteration_caps": list(CAPS),
        "input": {"path": str(ITERATION3), "sha256": digest(ITERATION3)},
        "bindings": {
            "driver": digest(Path(__file__)),
            "joint": digest(JOINT),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "rows": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
