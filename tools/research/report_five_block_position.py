#!/usr/bin/env python3
"""Evaluate sealed five-block refinements and compare chronological counterparts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt

from leo.analysis.research.regional_doppler import Region


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def distance_km(latitude_a, longitude_a, latitude_b, longitude_b):
    a1, a2 = math.radians(latitude_a), math.radians(latitude_b)
    da = a2 - a1
    dl = math.radians(longitude_b - longitude_a)
    value = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def load_sealed(path: Path) -> dict:
    result_path = path / "result.json"
    result = json.loads(result_path.read_text())
    seal = json.loads((path / "refinement-seal.json").read_text())
    checksum = (path / "result.sha256").read_text().strip()
    if (
        seal["result_digest"] != digest(result_path)
        or checksum != hashlib.sha256(result_path.read_bytes()).hexdigest()
        or result.get("position_truth_used") is not False
        or result.get("complete") is not True
        or not result.get("fits")
        or not all(item.get("converged") is True for item in result["fits"])
        or not seal.get("all_fits_converged")
    ):
        raise ValueError("unsealed or unqualified inference input")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh report output required")
    blocked_inputs = {}
    baseline_inputs = {}
    baseline_seal_path = args.baseline / "artifacts/inference-seal.json"
    baseline_seal = json.loads(baseline_seal_path.read_text())
    for start in ("sacramento", "reno", "denver"):
        for cohort in ("set", "single"):
            blocked_path = args.run_root / f"{start}-{cohort}-refinement-v2"
            blocked_inputs[(start, cohort)] = load_sealed(blocked_path)
            baseline_path = args.baseline / "artifacts" / f"{start}-{cohort}-refinement-v2.json"
            baseline = json.loads(baseline_path.read_text())
            authority = next(
                value["result.json"]
                for key, value in baseline_seal.items()
                if key.endswith(f"/{start}-{cohort}-refinement-v2")
            )
            if hashlib.sha256(baseline_path.read_bytes()).hexdigest() != authority:
                raise ValueError("chronological baseline differs from its inference seal")
            baseline_inputs[(start, cohort)] = baseline
    args.output.mkdir(parents=True)
    bindings = {
        "schema": "five-block-position-inference-bindings/v1",
        "truth_accessed": False,
        "five_block": {
            f"{start}-{cohort}": digest(
                args.run_root / f"{start}-{cohort}-refinement-v2/result.json"
            )
            for start, cohort in blocked_inputs
        },
        "chronological": {
            f"{start}-{cohort}": digest(
                args.baseline / "artifacts" / f"{start}-{cohort}-refinement-v2.json"
            )
            for start, cohort in baseline_inputs
        },
        "chronological_inference_seal_digest": digest(baseline_seal_path),
    }
    (args.output / "inference-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    truth_document = json.loads((args.baseline / "artifacts/summary.json").read_text())
    truth = truth_document["truth"]
    rows = []
    for start in ("sacramento", "reno", "denver"):
        for cohort in ("set", "single"):
            blocked_path = args.run_root / f"{start}-{cohort}-refinement-v2"
            blocked = blocked_inputs[(start, cohort)]
            baseline_path = args.baseline / "artifacts" / f"{start}-{cohort}-refinement-v2.json"
            baseline = baseline_inputs[(start, cohort)]
            region = Region(**blocked["region"])
            modes = []
            for fit in blocked["fits"]:
                latitude, longitude = region.coordinates(fit["east_km"], fit["north_km"])
                modes.append(
                    {
                        "latitude_deg": float(latitude),
                        "longitude_deg": float(longitude),
                        "training_score": fit["training_score"],
                        "converged": fit["converged"],
                    }
                )
            rows.append(
                {
                    "start": start,
                    "cohort": cohort,
                    "five_block": {
                        "latitude_deg": blocked["latitude_deg"],
                        "longitude_deg": blocked["longitude_deg"],
                        "horizontal_error_km": distance_km(
                            blocked["latitude_deg"],
                            blocked["longitude_deg"],
                            truth["latitude_deg"],
                            truth["longitude_deg"],
                        ),
                        "training_score": blocked["training_score"],
                        "heldout_score": blocked["heldout_score"],
                        "result_digest": digest(blocked_path / "result.json"),
                        "modes": modes,
                    },
                    "chronological": {
                        "latitude_deg": baseline["latitude_deg"],
                        "longitude_deg": baseline["longitude_deg"],
                        "horizontal_error_km": distance_km(
                            baseline["latitude_deg"],
                            baseline["longitude_deg"],
                            truth["latitude_deg"],
                            truth["longitude_deg"],
                        ),
                        "training_score": baseline["training_score"],
                        "heldout_score": baseline["heldout_score"],
                        "result_digest": digest(baseline_path),
                    },
                }
            )
    output = {
        "schema": "five-block-position-evaluation/v1",
        "purpose": "evaluation_only_after_sealed_inference",
        "truth": truth,
        "partition_interpretation": {
            "five_block": "full-span interpolation/shape CV",
            "chronological": "future forecasting",
            "scores_directly_comparable": False,
        },
        "results": rows,
    }
    (args.output / "evaluation.json").write_text(
        json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    figure, axes = plt.subplots(1, 3, figsize=(15, 5))
    for axis, cohort in zip(axes[:2], ("set", "single"), strict=True):
        selected = [row for row in rows if row["cohort"] == cohort]
        for row in selected:
            axis.scatter(
                row["chronological"]["longitude_deg"],
                row["chronological"]["latitude_deg"],
                marker="x",
                label=f"{row['start']} chronological",
            )
            axis.scatter(
                row["five_block"]["longitude_deg"],
                row["five_block"]["latitude_deg"],
                marker="o",
                label=f"{row['start']} five-block",
            )
        axis.scatter(
            truth["longitude_deg"],
            truth["latitude_deg"],
            marker="*",
            s=120,
            c="black",
            label="reference",
        )
        axis.set(
            title=f"{cohort.capitalize()} cohort",
            xlabel="Longitude (deg)",
            ylabel="Latitude (deg)",
        )
        axis.grid(alpha=0.25)
        axis.legend(fontsize=7)
    labels, chronological_error, blocked_error = [], [], []
    for row in rows:
        labels.append(f"{row['start'][:3]}-{row['cohort']}")
        chronological_error.append(row["chronological"]["horizontal_error_km"])
        blocked_error.append(row["five_block"]["horizontal_error_km"])
    positions = list(range(len(labels)))
    axes[2].scatter(chronological_error, positions, marker="x", label="chronological")
    axes[2].scatter(blocked_error, positions, marker="o", label="five-block")
    axes[2].set_xscale("log")
    axes[2].set_yticks(positions, labels)
    axes[2].set(title="Evaluation error", xlabel="Horizontal error (km, log scale)")
    axes[2].grid(alpha=0.25)
    axes[2].legend(fontsize=8)
    figure.suptitle("Chronological forecast versus five-block shape validation")
    figure.tight_layout()
    figure.savefig(args.output / "partition-position-comparison.png", dpi=180)
    plt.close(figure)


if __name__ == "__main__":
    main()
