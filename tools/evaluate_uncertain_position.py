"""Evaluate sealed position results at one site without tuning their models."""

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from replay_regional_doppler import digest, write_json

SCHEMA = "org.leo.research.uncertain-position-evaluation/v1"
EARTH_RADIUS_M = 6_371_008.8


def distance_m(latitude, longitude, truth_latitude, truth_longitude):
    latitude, longitude, truth_latitude, truth_longitude = map(
        math.radians, (latitude, longitude, truth_latitude, truth_longitude)
    )
    a = (
        math.sin((latitude - truth_latitude) / 2) ** 2
        + math.cos(latitude)
        * math.cos(truth_latitude)
        * math.sin((longitude - truth_longitude) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _score(row, truth):
    return {
        **row,
        "position_error_m": distance_m(
            row["latitude_deg"], row["longitude_deg"], truth[0], truth[1]
        ),
    }


def evaluate_benchmark(label, path, truth):
    document = json.loads(path.read_text())
    if document.get("schema") != "org.leo.research.position-weighting-benchmark/v1":
        raise ValueError(f"{path}: unsupported benchmark schema")
    if document.get("evaluation_location_used") or not document.get(
        "configuration_frozen_before_truth_evaluation"
    ):
        raise ValueError(f"{path}: benchmark was not sealed before evaluation")
    candidates = []
    for candidate in document["candidates"]:
        full = [_score(row, truth) for row in candidate["full_fits"]]
        deletions = []
        for row in candidate["deletion_fits"]:
            scored = _score(row, truth)
            reference = next(item for item in full if item["weighting"] == row["weighting"])
            scored["shift_from_full_fit_m"] = distance_m(
                row["latitude_deg"],
                row["longitude_deg"],
                reference["latitude_deg"],
                reference["longitude_deg"],
            )
            deletions.append(scored)
        summaries = []
        for weighting in document["configuration"]["weightings"]:
            for grouping in document["configuration"]["deletion_groups"]:
                rows = [
                    row
                    for row in deletions
                    if row["weighting"] == weighting and row["deletion_group"] == grouping
                ]
                shifts = np.asarray([row["shift_from_full_fit_m"] for row in rows])
                errors = np.asarray([row["position_error_m"] for row in rows])
                summaries.append(
                    {
                        "weighting": weighting,
                        "deletion_group": grouping,
                        "fits": len(rows),
                        "shift_median_m": float(np.median(shifts)),
                        "shift_max_m": float(np.max(shifts)),
                        "position_error_min_m": float(np.min(errors)),
                        "position_error_max_m": float(np.max(errors)),
                    }
                )
        candidates.append(
            {
                **{
                    key: value
                    for key, value in candidate.items()
                    if key not in {"full_fits", "deletion_fits"}
                },
                "full_fits": full,
                "deletion_fits": deletions,
                "deletion_summaries": summaries,
            }
        )
    return {
        "label": label,
        "kind": "weighting_benchmark",
        "source": str(path),
        "source_digest": digest(path),
        "configuration": document["configuration"],
        "candidates": candidates,
    }


def evaluate_inference(label, path, truth):
    document = json.loads(path.read_text())
    if document.get("evaluation_location_used"):
        raise ValueError(f"{path}: inference used the evaluation location")
    rows = []
    for row in document.get("models", []):
        if all(key in row for key in ["latitude_deg", "longitude_deg"]):
            scored = _score(row, truth)
            explicit = row.get("causal_comparison_eligible")
            if isinstance(explicit, bool):
                eligible = explicit
            elif not document.get("strictly_causal"):
                eligible = None
            elif document.get("future_tles_used_for_labelled_diagnostic_only"):
                known = {
                    "baseline": True,
                    "causal_phase_prior": True,
                    "future_tle_oracle_phase": False,
                }
                eligible = known.get(row.get("orbit_model"))
            else:
                eligible = True
            scored["causal_comparison_eligible"] = eligible
            if eligible is False:
                scored["comparison_exclusion_reason"] = (
                    "Source provenance labels this model unavailable at capture."
                )
            elif eligible is None:
                scored["comparison_exclusion_reason"] = (
                    "Source does not explicitly establish causal information availability."
                )
            rows.append(scored)
    if not rows:
        raise ValueError(f"{path}: no position models")
    return {
        "label": label,
        "kind": "sealed_inference",
        "source": str(path),
        "source_digest": digest(path),
        "models": rows,
    }


def _plot(result, output):
    points = []
    deletion = []

    def display(value):
        aliases = {
            "observation": "obs", "segment": "episode", "satellite": "sat",
            "fixed": "fixed UTC", "shared_recorded": "shared clock",
            "candidate_identity_mixture": "identity mixture",
        }
        return aliases.get(str(value), str(value).replace("_", " "))

    for source in result["sources"]:
        if source["kind"] == "weighting_benchmark":
            for candidate in source["candidates"]:
                for row in candidate["full_fits"]:
                    points.append(
                        {
                            "series": display(candidate["name"]),
                            "variant": display(row["weighting"]),
                            "error": row["position_error_m"],
                            "residual": row["evaluation_rms_hz"],
                        }
                    )
                for row in candidate["deletion_summaries"]:
                    deletion.append(
                        (
                            " · ".join(
                                [
                                    display(candidate["name"]),
                                    display(row["weighting"]),
                                    display(row["deletion_group"]),
                                ]
                            ),
                            row["shift_max_m"],
                        )
                    )
        else:
            for index, row in enumerate(source["models"]):
                fallback = "fixed identity" if row.get("clock_model") else f"model {index}"
                name = row.get("method", row.get("orbit_model", fallback))
                series = row.get("cohort") or name or source["label"]
                variant = row.get("weighting") or row.get("clock_model") or source["label"]
                if row.get("clock_model") and not row.get("cohort"):
                    variant = row["clock_model"]
                points.append(
                    {
                        "series": display(series),
                        "variant": display(variant),
                        "error": row["position_error_m"],
                        "residual": row.get("evaluation_rms_hz", np.nan),
                    }
                )
    columns = 2 if deletion else 1
    fig, axes = plt.subplots(
        1, columns, figsize=(14, 6) if deletion else (8, 6), layout="constrained"
    )
    axes = np.atleast_1d(axes)
    series = list(dict.fromkeys(row["series"] for row in points))
    variants = list(dict.fromkeys(row["variant"] for row in points))
    colors = {name: plt.get_cmap("tab10")(index % 10) for index, name in enumerate(series)}
    markers = ["o", "s", "^", "D", "P", "X"]
    marker_by_variant = {name: markers[index % len(markers)] for index, name in enumerate(variants)}
    for row in points:
        axes[0].scatter(
            row["error"],
            row["residual"],
            color=colors[row["series"]],
            marker=marker_by_variant[row["variant"]],
            s=58,
            label=f"{row['series']} · {row['variant']}",
        )
    axes[0].set(
        xlabel="Position error at evaluation site (m)",
        ylabel="Randomized held-out residual RMS (Hz)",
        title="Residual fit and position accuracy are separate outcomes",
    )
    axes[0].grid(alpha=0.2)
    axes[0].legend(fontsize=8, frameon=False, loc="best")
    if deletion:
        x = np.arange(len(deletion))
        axes[1].bar(x, [row[1] for row in deletion], color="#457b9d")
        axes[1].set_xticks(x, [row[0] for row in deletion], rotation=65, ha="right", fontsize=7)
        axes[1].set(
            ylabel="Maximum shift from full fit (m)",
            title="Predefined four-fold deletion influence",
        )
        axes[1].grid(axis="y", alpha=0.2)
    has_weighting_benchmark = any(
        source["kind"] == "weighting_benchmark" for source in result["sources"]
    )
    fig.suptitle(
        "Single-site sealed evaluation · uncertainties are dataset-conditional"
        if has_weighting_benchmark
        else "Single-site sealed evaluation · reference used only after sealing"
    )
    fig.savefig(output / "position-weighting-evaluation.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth-latitude", type=float, required=True)
    parser.add_argument("--truth-longitude", type=float, required=True)
    parser.add_argument(
        "--benchmark", nargs=2, action="append", metavar=("LABEL", "PATH"), default=[]
    )
    parser.add_argument(
        "--inference", nargs=2, action="append", metavar=("LABEL", "PATH"), default=[]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output directory required")
    args.output.mkdir(parents=True)
    truth = (args.truth_latitude, args.truth_longitude)
    sources = [evaluate_benchmark(label, Path(path), truth) for label, path in args.benchmark]
    sources.extend(evaluate_inference(label, Path(path), truth) for label, path in args.inference)
    if not sources:
        raise ValueError("at least one sealed result is required")
    result = {
        "schema": SCHEMA,
        "truth": {"latitude_deg": truth[0], "longitude_deg": truth[1]},
        "single_site_evaluation": True,
        "universal_position_uncertainty_claimed": False,
        "model_selection_or_tuning_from_position_error": False,
        "sources": sources,
    }
    _plot(result, args.output)
    write_json(args.output / "evaluation.json", result)


if __name__ == "__main__":
    main()
