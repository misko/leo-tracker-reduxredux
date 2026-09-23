#!/usr/bin/env python3
"""Validate frozen five-scan artifacts and render evaluation-only summaries."""

import hashlib
import json
import math
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
CACHE = Path("/home/mouse9911/.cache/leo-research/shared-orbit-rate-cache-v1")
REFERENCE_SOURCE = Path(
    "/home/mouse9911/gits/leo-standard-position-methods/"
    "reports/2026_09_22_joint_blind_geometry/evaluation-reference.json"
)
VERSIONS = {"sacramento": 7, "reno": 8, "denver": 7}


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def distance_km(a_lat, a_lon, b_lat, b_lon):
    a1, a2 = math.radians(a_lat), math.radians(b_lat)
    da = a2 - a1
    dl = math.radians(b_lon - a_lon)
    value = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(value))


def main():
    reference = read(REFERENCE_SOURCE)
    single = read(CACHE / "three-region-single-evaluation-v1.json")
    controls = read(CACHE / "sacramento-set-controls-v2.json")
    original_heldout = sum(
        row["arms"]["original_orbit"]["heldout_log_predictive"]
        for row in controls["sessions"]
    )
    provenance = {
        "schema": "five-scan-shared-orbit-provenance/v1",
        "truth_accessed_during_fit": False,
        "evaluation_reference": {
            "path": str(REFERENCE_SOURCE),
            "digest": digest(REFERENCE_SOURCE),
        },
        "fits": {},
        "exact_replays": {},
        "cache_manifests": {},
        "supporting_inputs": {},
    }
    rows = []
    association_modes = {}
    for region in ("sacramento", "reno", "denver"):
        version = VERSIONS[region]
        fit_path = CACHE / f"{region}-set-joint-v{version}-resumed.json"
        exact_dir = CACHE / f"{region}-set-exact-v{version}"
        exact_path = exact_dir / "result.json"
        fit, exact = read(fit_path), read(exact_path)
        fit_digest = digest(fit_path)
        exact_digest = digest(exact_path)
        if (
            fit.get("converged") is not True
            or fit.get("truth_accessed") is not False
            or exact.get("truth_accessed") is not False
            or exact.get("score_agreement") is not True
            or exact.get("shared_prior_count") != 1
            or exact.get("fit_digest") != fit_digest
            or exact.get("evaluated_cases") != 1_819_178
        ):
            raise ValueError(f"unqualified fit or exact replay: {region}")
        for session, expected in fit["manifest_digests"].items():
            candidates = list(CACHE.glob(f"{session}/manifest.json")) + list(
                Path("/tmp/shared-orbit-rate-cache-v1").glob(f"{session}/manifest.json")
            )
            if len(candidates) != 1 or digest(candidates[0]) != expected:
                raise ValueError(f"cache manifest binding differs: {session}")
            provenance["cache_manifests"][session] = {
                "path": str(candidates[0]), "digest": expected
            }
        provenance["fits"][region] = {"path": str(fit_path), "digest": fit_digest}
        provenance["exact_replays"][region] = {
            "path": str(exact_path), "digest": exact_digest,
            "input_and_receipt_files": [
                {"path": str(path), "digest": digest(path)}
                for path in sorted(exact_dir.glob("*.json"))
            ],
        }
        shutil.copyfile(exact_path, HERE / "exact" / f"{region}-result.json")
        error = distance_km(
            fit["latitude_deg"], fit["longitude_deg"],
            reference["latitude_deg"], reference["longitude_deg"],
        )
        rows.append(
            {
                "region": region,
                "horizontal_error_km": error,
                "latitude_deg": fit["latitude_deg"],
                "longitude_deg": fit["longitude_deg"],
                "negative_log_posterior": fit["negative_log_posterior"],
                "heldout_log_predictive": fit["heldout_log_predictive"],
                "projected_gradient_max": fit["projected_gradient_max"],
                "evaluations": fit["evaluations"],
                "convergence_message": fit["message"],
                "exact_cases": exact["evaluated_cases"],
                "exact_maximum_doppler_error_hz": exact["maximum_doppler_error_hz"],
                "exact_objective_difference": exact["objective_difference"],
                "exact_heldout_difference": exact["heldout_difference"],
            }
        )
        rates = {item["norad"]: item["rate_s_h"] for item in fit["rates"]}
        association_modes[region] = {"rates_s_h": {str(n): rates[n] for n in (55604, 63792)}}
        for norad in (55604, 63792):
            weights = []
            ranks = []
            for episode in fit["associations"]:
                if not episode["episode_id"].startswith("scan-fw-e3bc0741ecf02704/"):
                    continue
                for rank, candidate in enumerate(episode["top_candidates"], 1):
                    if candidate["norad"] == norad:
                        weights.append(candidate["weight"])
                        ranks.append(rank)
            association_modes[region][str(norad)] = {
                "top_ten_episode_count": len(weights),
                "weight_sum": sum(weights),
                "maximum_weight": max(weights) if weights else 0,
                "ranks": ranks,
            }
    for path in (
        CACHE / "three-region-single-evaluation-v1.json",
        CACHE / "two-region-set-evaluation-v1.json",
        CACHE / "sacramento-set-controls-v2.json",
    ):
        provenance["supporting_inputs"][path.name] = {
            "path": str(path), "digest": digest(path)
        }
    single_by_region = {row["region"]: row for row in single["rows"]}
    best_objective = min(row["negative_log_posterior"] for row in rows)
    for row in rows:
        row["objective_above_best"] = row["negative_log_posterior"] - best_objective
        row["single_scan_horizontal_error_km"] = single_by_region[row["region"]][
            "horizontal_error_km"
        ]
        row["five_minus_single_error_km"] = (
            row["horizontal_error_km"] - row["single_scan_horizontal_error_km"]
        )
        row["heldout_gain_over_original_orbit"] = (
            row["heldout_log_predictive"] - original_heldout
        )
    summary = {
        "schema": "five-scan-shared-orbit-evaluation/v1",
        "purpose": "evaluation_only_after_blind_fits_and_exact_replay",
        "reference": reference,
        "dataset": {
            "session_count": 5,
            "track_count": 165,
            "observation_count": 5432,
            "capture_span_h": 3.2,
            "holdout": "within-scan interleaved observations spanning all five scans; not whole-scan holdout",
        },
        "matched_control_original_orbit_heldout_log_predictive": original_heldout,
        "rows": rows,
        "association_mode_diagnostic": association_modes,
        "interpretation_limits": [
            "Composite MAP association weights are not calibrated posterior probabilities.",
            "Three local starts do not establish the global mode or calibrated confidence.",
            "The fitted shared orbital-rate nuisance is not a corrected-orbit acquisition.",
            "The error reduction does not isolate or prove an incremental geometry gain.",
            "The separate eight-hour whole-scan study remains pending.",
        ],
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (HERE / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")

    labels = [row["region"].title() for row in rows]
    matrix = np.array(
        [[row["single_scan_horizontal_error_km"], row["horizontal_error_km"]] for row in rows]
    )
    fig, ax = plt.subplots(figsize=(8, 5))
    image = ax.imshow(matrix, cmap="Blues_r", aspect="auto", vmin=0, vmax=6)
    for i in range(3):
        for j in range(2):
            ax.text(j, i, f"{matrix[i, j]:.3f} km", ha="center", va="center", fontsize=11)
    ax.set(xticks=[0, 1], xticklabels=["Single scan", "Five scans"], yticks=range(3), yticklabels=labels)
    ax.set_title("Evaluation horizontal error · local starts × dataset size")
    fig.colorbar(image, ax=ax, label="Horizontal error (km)")
    fig.tight_layout()
    fig.savefig(HERE / "position-error-matrix.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    objectives = [row["objective_above_best"] for row in rows]
    heldout = [row["heldout_log_predictive"] for row in rows]
    axes[0].bar(labels, objectives)
    axes[0].set(ylabel="NLP above best (lower is better)", title="Local MAP objective modes")
    axes[1].bar(labels, heldout, label="Joint fit")
    axes[1].axhline(original_heldout, color="black", linestyle="--", label="Original-orbit control")
    axes[1].set(ylabel="Held-out log predictive (higher is better)", title="Within-scan held-out score")
    axes[1].legend(fontsize=8)
    for axis in axes:
        axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(HERE / "mode-and-heldout-scores.png", dpi=180)
    plt.close(fig)
    artifacts = {}
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and path.name != "artifact-manifest.json":
            artifacts[str(path.relative_to(HERE))] = {
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
    (HERE / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "schema": "five-scan-shared-orbit-artifact-manifest/v1",
                "files": artifacts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
