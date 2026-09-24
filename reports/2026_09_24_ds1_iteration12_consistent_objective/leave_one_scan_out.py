#!/usr/bin/env python3
"""Reference-free leave-one-whole-scan-out stability over iteration-12 finalists."""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
RUN = HERE / "run.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sliced(support: Any, omitted_session: str) -> Any:
    mask = np.asarray(
        [not str(name).startswith(f"{omitted_session}:") for name in support.track], dtype=bool
    )
    if not np.any(mask):
        raise ValueError("omission removed every observation")
    support_type = type(support)
    kept_weights = {
        name: weight
        for name, weight in support.weights.items()
        if not name.startswith(f"{omitted_session}:")
    }
    return support_type(
        measured=support.measured[mask],
        nominal=support.nominal[mask],
        sensitivity_hz_s=support.sensitivity_hz_s[mask],
        age_h=support.age_h[mask],
        source=support.source[mask],
        track=support.track[mask],
        weights=kept_weights,
        associations=[row for row in support.associations if row["session_id"] != omitted_session],
    )


def compact(fit: dict[str, Any]) -> dict[str, Any]:
    return {
        "loss": fit["selection_objective"],
        "converged": fit["converged"],
        "iterations": fit["iterations"],
        "rate_boundary_count": fit["rate_boundary_count"],
    }


def evaluate(task: tuple[int, str, dict[str, Any]]) -> dict[str, Any]:
    rank, group, candidate = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    run = load(RUN, f"i12_loo_run_{os.getpid()}")
    iteration10 = load(run.ITER10_RUN, f"i12_loo_i10_{os.getpid()}")
    iteration9 = load(iteration10.ITER9_RUN, f"i12_loo_i9_{os.getpid()}")
    iteration8 = load(iteration9.ITER8_RUN, f"i12_loo_i8_{os.getpid()}")
    joint = load(run.JOINT, f"i12_loo_joint_{os.getpid()}")
    existing = load(run.RUNNER, f"i12_loo_existing_{os.getpid()}")
    orbit = load(run.ORBIT, f"i12_loo_orbit_{os.getpid()}")
    source = json.loads(iteration8.source_path(group).read_text())
    engine = existing.FullObservationEngine(existing.validate_task(iteration8.source_task(source)))
    tau = candidate["best_exact_by_group"][group]["tau_s"]
    support = joint.hard_support(
        engine, orbit, candidate["latitude_deg"], candidate["longitude_deg"], tau
    )
    rows = {"full": compact(run.profile_consistent(support))}
    for session in source["session_ids"]:
        rows[session] = compact(run.profile_consistent(sliced(support, session)))
    return {
        "candidate_exact_rank": rank,
        "group_id": group,
        "latitude_deg": candidate["latitude_deg"],
        "longitude_deg": candidate["longitude_deg"],
        "tau_s": tau,
        "fits": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("workers must be 1..8")
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference is not sealed")
    run = load(RUN, "i12_loo_main_run")
    tasks = [
        (rank, group, candidate)
        for rank, candidate in enumerate(inference["exact_finalists"], 1)
        for group in run.GROUPS
    ]
    begun = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        fits = list(pool.map(evaluate, tasks, chunksize=1))

    sessions = {
        group: sorted(
            key for row in fits if row["group_id"] == group for key in row["fits"] if key != "full"
        )
        for group in run.GROUPS
    }
    sessions = {group: sorted(set(values)) for group, values in sessions.items()}

    def score(rank: int, omitted_group: str | None, omitted_session: str | None) -> float:
        losses = []
        for group in run.GROUPS:
            row = next(
                value
                for value in fits
                if value["candidate_exact_rank"] == rank and value["group_id"] == group
            )
            fit_key = omitted_session if group == omitted_group else "full"
            losses.append(row["fits"][fit_key]["loss"])
        return float(np.mean(losses))

    selections = []
    cases = [(None, None)] + [
        (group, session) for group in run.GROUPS for session in sessions[group]
    ]
    for omitted_group, omitted_session in cases:
        scored = [
            {
                "candidate_exact_rank": rank,
                "balanced_cap800_loss": score(rank, omitted_group, omitted_session),
            }
            for rank in range(1, len(inference["exact_finalists"]) + 1)
        ]
        scored.sort(key=lambda row: (row["balanced_cap800_loss"], row["candidate_exact_rank"]))
        selections.append(
            {
                "omitted_group": omitted_group,
                "omitted_session": omitted_session,
                "winner_exact_rank": scored[0]["candidate_exact_rank"],
                "winner_balanced_cap800_loss": scored[0]["balanced_cap800_loss"],
                "runner_margin": scored[1]["balanced_cap800_loss"]
                - scored[0]["balanced_cap800_loss"],
                "ranking": scored,
            }
        )
    payload = {
        "schema": "ds1-iteration12-leave-one-whole-scan-out/v1",
        "partition": "train",
        "reference_used": False,
        "scope": (
            f"{len(inference['exact_finalists'])} exact finalists; cap-800 surrogate "
            "support; exact-selected tau per group"
        ),
        "elapsed_s": time.perf_counter() - begun,
        "workers": args.workers,
        "fits": fits,
        "selections": selections,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration12-leave-one-scan-out.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    omitted = [row for row in selections if row["omitted_session"] is not None]
    counts = np.bincount(
        [row["winner_exact_rank"] for row in omitted],
        minlength=len(inference["exact_finalists"]) + 1,
    )[1:]
    figure, axis = plt.subplots(figsize=(7, 3.5), constrained_layout=True)
    axis.bar(np.arange(1, len(counts) + 1), counts)
    axis.set(
        xlabel="iteration-12 exact finalist rank",
        ylabel="leave-one-scan-out wins",
        title="Whole-scan omission stability (12 TRAIN scans)",
        xticks=np.arange(1, len(counts) + 1),
    )
    figure.savefig(args.output_dir / "iteration12-leave-one-scan-out.png", dpi=180)
    print(
        json.dumps(
            {
                "elapsed_s": payload["elapsed_s"],
                "winner_counts_by_exact_rank": counts.tolist(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
