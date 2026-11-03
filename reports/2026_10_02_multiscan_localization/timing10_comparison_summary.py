"""Postseal paired reporting for every declared timing10/grouped unit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from evaluate_profile_batch import evaluate_unit
from timing10_comparison import PROTOCOL, ROOT, digest, units


def summarize(rows):
    summaries = []
    for dataset in ("DS10", "DS11"):
        for size in (1, 2, 4):
            population = [row for row in rows if row["dataset"] == dataset and row["size"] == size]
            paired = [row for row in population if all(
                row[arm]["status"] == "evaluated" for arm in ("legacy", "grouped")
            )]
            result = {"dataset": dataset, "size": size, "requested": len(population),
                      "paired_evaluated": len(paired)}
            for arm in ("legacy", "grouped"):
                errors = np.asarray([row[arm]["error_km"] for row in paired])
                result[arm] = {
                    "median_error_km": float(np.median(errors)) if len(errors) else None,
                    "p90_error_km": float(np.percentile(errors, 90)) if len(errors) else None,
                    "maximum_error_km": float(np.max(errors)) if len(errors) else None,
                    "sub_km_count": int(np.sum(errors < 1)),
                    "resolved_count": sum(row[arm]["selection_resolved"] for row in paired),
                    "leader_converged_count": sum(row[arm]["leader_converged"] for row in paired),
                    "pending_or_failed": sum(
                        row[arm]["status"] != "evaluated" for row in population
                    ),
                }
            result["grouped_lower_error_count"] = sum(
                row["grouped"]["error_km"] < row["legacy"]["error_km"] for row in paired
            )
            summaries.append(result)
    return summaries


def collect():
    source_hashes = {str(PROTOCOL): digest(PROTOCOL), str(Path(__file__)): digest(__file__)}
    rows = []
    for dataset, unit in units():
        row = {"dataset": dataset, "size": unit["size"], "unit_id": unit["unit_id"]}
        grouped_run = ("finite-set-tau-profile-v1" if unit["size"] == 1
                       else "grouped-timing-profile-joint-v1")
        parents = []
        for arm, run_id in (("legacy", "legacy-timing10-cohort-v1"), ("grouped", grouped_run)):
            directory = ROOT / "runs" / run_id / unit["unit_id"]
            path = directory / "fit.json"
            if not path.exists():
                failure = directory / "failure.json"
                row[arm] = {"status": "failed" if failure.exists() else "pending", "run_id": run_id}
                if failure.exists():
                    source_hashes[str(failure)] = digest(failure)
                    row[arm]["failure"] = json.loads(failure.read_text())
                continue
            receipt = json.loads(path.read_text())
            if receipt["unit"] != unit:
                raise ValueError("comparison receipt unit does not match frozen selection")
            evaluation = evaluate_unit(unit["unit_id"], run_id)
            source_hashes[str(path)] = digest(path)
            evaluation_path = directory / "evaluation.json"
            source_hashes[str(evaluation_path)] = digest(evaluation_path)
            parents.append(receipt.get("grouped_source_sha256", receipt.get("source_fit_sha256")))
            row[arm] = {
                "status": "evaluated", "run_id": run_id,
                "error_km": evaluation["selected"]["maximum_reference_error_km"],
                "selection_resolved": evaluation["selection_resolved"],
                "leader_converged": evaluation["selected"]["success"],
                "leader_status": evaluation["selected"]["status"],
                "satellite_count": evaluation["selected"]["satellite_count"],
                "elapsed_s": receipt.get("elapsed_s"),
            }
        if len(parents) == 2 and parents[0] != parents[1]:
            raise ValueError("comparison arms do not share the same frozen grouped input authority")
        rows.append(row)
    if any(digest(path) != expected for path, expected in source_hashes.items()):
        raise RuntimeError("comparison sources changed during reporting")
    return {
        "schema": "timing10-grouped-comparison/v1", "source_hashes": source_hashes,
        "rows": rows, "summary": summarize(rows),
        "complete": all(row[arm]["status"] == "evaluated" for row in rows
                        for arm in ("legacy", "grouped")),
        "scope": json.loads(PROTOCOL.read_text()),
    }


def plot(receipt, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for dataset, axis in zip(("DS10", "DS11"), axes, strict=True):
        for size, marker in ((1, "o"), (2, "s"), (4, "^")):
            rows = [row for row in receipt["rows"] if row["dataset"] == dataset
                    and row["size"] == size and all(row[arm]["status"] == "evaluated"
                                                   for arm in ("legacy", "grouped"))]
            axis.scatter([row["legacy"]["error_km"] for row in rows],
                         [row["grouped"]["error_km"] for row in rows], marker=marker,
                         label=f"{size} capture(s), n={len(rows)}", alpha=.8)
        axis.plot([.01, 300], [.01, 300], "k--", linewidth=.8)
        axis.axhline(1, color="gray", linestyle=":")
        axis.axvline(1, color="gray", linestyle=":")
        axis.set(xscale="log", yscale="log", xlim=(.01, 300), ylim=(.01, 300),
                 title=dataset, xlabel="Legacy timing ±10s, fixed RX ±50Hz/s: error km",
                 ylabel="Grouped timing-profile: error km")
        axis.legend()
        axis.grid(alpha=.2)
    figure.suptitle("All-data conditional comparison; below diagonal favors grouped\n"
                   "Unresolved fits retained; correlated single/pair/quad units")
    figure.savefig(output.with_suffix(".png"), dpi=160)
    figure.savefig(output.with_suffix(".svg"))
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    receipt = collect()
    with arguments.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    plot(receipt, arguments.output)
    print(json.dumps({"complete": receipt["complete"], "summary": receipt["summary"]}, indent=2))
