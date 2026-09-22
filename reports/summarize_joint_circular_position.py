#!/usr/bin/env python3
"""Truth-gated summary of six sealed joint circular-position diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt

CENTERS = ("sacramento", "reno", "denver")
COHORTS = ("single", "set")
ARMS = (
    "uniform-factor-control",
    "sigma-3000-outlier-0.05",
    "sigma-3000-outlier-0.2",
    "sigma-10000-outlier-0.05",
    "sigma-10000-outlier-0.2",
    "sigma-30000-outlier-0.05",
    "sigma-30000-outlier-0.2",
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def content_digest(value: dict) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def parse_input(value: str) -> tuple[tuple[str, str], Path]:
    try:
        center, cohort, path = value.split(":", 2)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected CENTER:COHORT:RESULT") from error
    if center not in CENTERS or cohort not in COHORTS or not path:
        raise argparse.ArgumentTypeError("unknown center/cohort or empty result path")
    return (center, cohort), Path(path)


def load_result(path: Path) -> dict:
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.with_name("result.sha256").read_text().strip() != checksum:
        raise ValueError(f"result checksum mismatch: {path}")
    value = json.loads(path.read_text())
    if (
        value.get("schema") != "blind-joint-circular-position-refinement/v1"
        or value.get("content_digest") != content_digest(value)
        or value.get("position_truth_used") is not False
        or value.get("partition")
        != "five-chronological-blocks-train-0-2-4-heldout-1-3-v1"
    ):
        raise ValueError(f"unsealed or incompatible result: {path}")
    names = [row.get("arm") for row in value.get("arms", [])]
    if tuple(names) != ARMS or len(names) != len(set(names)):
        raise ValueError(f"result does not contain the declared seven arms: {path}")
    return value


def haversine_km(latitude: float, longitude: float, reference: dict) -> float:
    lat1, lat2 = map(math.radians, (latitude, float(reference["latitude_deg"])))
    dlat = lat2 - lat1
    dlon = math.radians(float(reference["longitude_deg"]) - longitude)
    term = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(term))


def leader(track: dict) -> tuple[str, int | None]:
    null = float(track["null_weight"])
    candidates = track.get("candidates", [])
    if not candidates or null >= float(candidates[0]["circular_weight"]):
        return "null", None
    return "candidate", int(candidates[0]["norad"])


def association_summary(arm: dict, uniform: dict) -> dict:
    baseline_rows = [
        ((row["session_id"], row["episode_id"]), row) for row in uniform["tracks"]
    ]
    baseline = dict(baseline_rows)
    if len(baseline) != len(baseline_rows):
        raise ValueError("uniform control contains duplicate track identities")
    changed = 0
    null_weights = []
    actual_rows = [
        ((row["session_id"], row["episode_id"]), row) for row in arm["tracks"]
    ]
    actual_keys = [key for key, _row in actual_rows]
    if len(actual_keys) != len(set(actual_keys)) or set(actual_keys) != set(baseline):
        raise ValueError("arm track inventory differs from uniform control")
    for key, row in actual_rows:
        changed += leader(row) != leader(baseline[key])
        null_weights.append(float(row["null_weight"]))
    return {
        "track_count": len(null_weights),
        "leader_changes_from_uniform": changed,
        "null_weight_mean": sum(null_weights) / len(null_weights),
        "null_weight_over_half_count": sum(value > 0.5 for value in null_weights),
    }


def group_channel_composition(arm: dict) -> list[dict]:
    groups: dict[tuple[int, str], dict[int, int]] = {}
    for track in arm["tracks"]:
        key = int(track["receiver_id"]), str(track["pilot_edge"])
        channels = groups.setdefault(key, {})
        channel = int(track["channel"])
        channels[channel] = channels.get(channel, 0) + 1
    return [
        {
            "receiver_id": key[0],
            "pilot_edge": key[1],
            "channel_track_counts": {
                str(channel): count for channel, count in sorted(value.items())
            },
            "assumption": "one constant native-Hz nuisance coordinate spans these channels",
        }
        for key, value in sorted(groups.items())
    ]


def bind_inputs(inputs: list[tuple[tuple[str, str], Path]], output: Path) -> dict:
    paths = dict(inputs)
    expected = {(center, cohort) for center in CENTERS for cohort in COHORTS}
    if len(inputs) != 6 or len(paths) != 6 or set(paths) != expected:
        raise ValueError("exactly one result for every center/cohort is required")
    results = {key: load_result(path) for key, path in paths.items()}
    for (center, cohort), result in results.items():
        expected_counts = (39, 1415) if cohort == "single" else (165, 5432)
        actual_counts = result.get("track_count"), result.get("observation_count")
        if actual_counts != expected_counts:
            raise ValueError(f"cohort accounting mismatch for {center}-{cohort}")
    bindings = {
        "schema": "joint-circular-position-inference-bindings/v1",
        "truth_accessed": False,
        "center_labels": (
            "caller-supplied labels; the result schema does not independently encode center"
        ),
        "inputs": {
            f"{center}-{cohort}": {
                "path": str(paths[(center, cohort)]),
                "result_digest": digest(paths[(center, cohort)]),
                "content_digest": results[(center, cohort)]["content_digest"],
                "complete": results[(center, cohort)].get("complete"),
                "qualification": results[(center, cohort)].get("qualification"),
            }
            for center in CENTERS
            for cohort in COHORTS
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "inference-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return results


def summarize(results: dict, reference: dict, reference_path: Path) -> dict:
    if set(reference) < {"latitude_deg", "longitude_deg"}:
        raise ValueError("reference requires latitude_deg and longitude_deg")
    runs = []
    for center in CENTERS:
        for cohort in COHORTS:
            result = results[(center, cohort)]
            uniform = result["arms"][0]
            arms = []
            for arm in result["arms"]:
                association = association_summary(arm, uniform)
                arms.append(
                    {
                        "arm": arm["arm"],
                        "status": {
                            "all_fits_converged": all(
                                fit.get("converged") is True for fit in arm["fits"]
                            ),
                            "any_bound_hit": any(
                                fit.get("bound_hit") is True for fit in arm["fits"]
                            ),
                            "fit_count": len(arm["fits"]),
                        },
                        "latitude_deg": arm["latitude_deg"],
                        "longitude_deg": arm["longitude_deg"],
                        "error_km": haversine_km(
                            arm["latitude_deg"], arm["longitude_deg"], reference
                        ),
                        "training_score": arm["training_score"],
                        "heldout_score": arm["heldout_score"],
                        "training_delta_from_uniform": arm["training_score"]
                        - uniform["training_score"],
                        "heldout_delta_from_uniform": arm["heldout_score"]
                        - uniform["heldout_score"],
                        "pruning_log_error_bound": arm["pruning_log_error_bound"],
                        "association": association,
                        "groups": arm["groups"],
                    }
                )
            runs.append(
                {
                    "center": center,
                    "cohort": cohort,
                    "complete": result.get("complete"),
                    "qualification": result.get("qualification"),
                    "qualification_failures": result.get("qualification_failures", []),
                    "track_count": result["track_count"],
                    "observation_count": result["observation_count"],
                    "configuration": result["configuration"],
                    "uniform_baseline_parity": result["uniform_baseline_parity"],
                    "elapsed_s": result["elapsed_s"],
                    "peak_rss_kib": result["peak_rss_kib"],
                    "group_channel_composition": group_channel_composition(uniform),
                    "arms": arms,
                }
            )
    return {
        "schema": "joint-circular-position-evaluation/v1",
        "truth_accessed_after_inference_bindings": True,
        "reference": {
            "latitude_deg": float(reference["latitude_deg"]),
            "longitude_deg": float(reference["longitude_deg"]),
            "source_digest": digest(reference_path),
        },
        "interpretation": {
            "heldout": "within-track five-block interpolation at a training-selected position",
            "association": "uncalibrated soft identity weights at each arm's selected position",
            "uncertainty": "no calibrated confidence interval",
        },
        "runs": runs,
    }


def plot(summary: dict, output: Path) -> None:
    colors = {"single": "tab:orange", "set": "tab:blue"}
    markers = {"sacramento": "o", "reno": "s", "denver": "^"}
    figure, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    position, errors, heldout, association = axes.flat
    for run in summary["runs"]:
        x = range(len(ARMS))
        label = f"{run['center']} {run['cohort']}"
        color = colors[run["cohort"]]
        marker = markers[run["center"]]
        position.plot(
            [row["longitude_deg"] for row in run["arms"]],
            [row["latitude_deg"] for row in run["arms"]],
            marker=marker,
            color=color,
            alpha=0.75,
            label=label,
        )
        errors.plot(
            x,
            [row["error_km"] for row in run["arms"]],
            marker=marker,
            color=color,
            alpha=0.75,
        )
        heldout.plot(
            x,
            [row["heldout_delta_from_uniform"] for row in run["arms"]],
            marker=marker,
            color=color,
            alpha=0.75,
        )
        association.plot(
            x,
            [
                row["association"]["leader_changes_from_uniform"]
                for row in run["arms"]
            ],
            marker=marker,
            color=color,
            alpha=0.75,
        )
    ref = summary["reference"]
    position.scatter(
        ref["longitude_deg"],
        ref["latitude_deg"],
        marker="*",
        s=130,
        color="black",
        label="evaluation reference",
    )
    position.set(
        xlabel="longitude (deg)",
        ylabel="latitude (deg)",
        title="Training-selected local solutions",
    )
    position.legend(fontsize=7, ncol=2)
    for axis, title, ylabel in (
        (errors, "Post-seal evaluation error", "great-circle error (km)"),
        (heldout, "Heldout score change from uniform", "conditional heldout Δ"),
        (association, "Association leader changes", "tracks changed from uniform"),
    ):
        labels = [
            name.replace("sigma-", "σ").replace("-outlier-", "/") for name in ARMS
        ]
        axis.set_xticks(
            range(len(ARMS)), labels, rotation=35, ha="right", fontsize=7
        )
        axis.set(title=title, ylabel=ylabel)
        axis.grid(alpha=0.25)
    heldout.axhline(0, color="black", linewidth=0.8)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=parse_input, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = bind_inputs(args.input, args.output)
    reference = json.loads(args.reference.read_text())
    summary = summarize(results, reference, args.reference)
    summary["content_digest"] = content_digest(summary)
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    plot(summary, args.output / "joint-circular-position.png")


if __name__ == "__main__":
    main()
