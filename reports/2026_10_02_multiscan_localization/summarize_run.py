"""Account for every frozen unit, including missing and failed fits."""

import argparse
import json
from pathlib import Path

import numpy as np
from selection import ROOT


def error_quantiles(errors):
    if not errors:
        return None
    return dict(
        zip(
            ("min", "median", "p90", "max"),
            np.quantile(errors, [0, 0.5, 0.9, 1]).tolist(),
            strict=True,
        )
    )


def summarize(root, run_id):
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text())
    rows = []
    for dataset, population in selection["datasets"].items():
        for unit in population["units"]:
            folder = root / "runs" / run_id / unit["unit_id"]
            row = {"dataset": dataset, "unit_id": unit["unit_id"], "size": unit["size"]}
            evaluation = folder / "evaluation.json"
            if evaluation.exists():
                result = json.loads(evaluation.read_text())
                if result["unit_id"] != unit["unit_id"]:
                    raise ValueError("Evaluation unit identity mismatch")
                row.update(
                    status="converged" if result["success"] else "unresolved",
                    error_km=result["maximum_reference_error_km"],
                    elapsed_s=result["elapsed_s"],
                )
            elif (folder / "failure.json").exists():
                row["status"] = "failed"
            else:
                row["status"] = "incomplete" if folder.exists() else "not_started"
            rows.append(row)
    groups = []
    for dataset in selection["datasets"]:
        for size in (1, 2, 4):
            subset = [row for row in rows if row["dataset"] == dataset and row["size"] == size]
            errors = [row["error_km"] for row in subset if row["status"] == "converged"]
            provisional = [row["error_km"] for row in subset if "error_km" in row]
            groups.append(
                {
                    "dataset": dataset,
                    "size": size,
                    "expected": len(subset),
                    "status_counts": {
                        status: sum(row["status"] == status for row in subset)
                        for status in (
                            "converged",
                            "unresolved",
                            "failed",
                            "incomplete",
                            "not_started",
                        )
                    },
                    "converged_sub_km": sum(error < 1 for error in errors),
                    "converged_error_km_quantiles": error_quantiles(errors),
                    "provisional_estimate_count": len(provisional),
                    "provisional_error_km_quantiles": error_quantiles(provisional),
                }
            )
    return {
        "run_id": run_id,
        "units": rows,
        "groups": groups,
        "scope": "Converged quantiles exclude unresolved fits; provisional quantiles include "
        "every completed estimate regardless of convergence. All failures and missing units "
        "remain counted. Provisional accuracy does not establish optimization success.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    print(json.dumps(summarize(ROOT, args.run_id), indent=2))


if __name__ == "__main__":
    main()
