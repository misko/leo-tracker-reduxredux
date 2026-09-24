#!/usr/bin/env python3
"""Derive a reference-free, source-tempered weighting from sealed DS1 surfaces."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ITERATIONS = {
    "iteration8": ROOT / "reports/2026_09_24_ds1_iteration8_joint_groups/inference.json",
    "iteration9": ROOT / "reports/2026_09_24_ds1_iteration9_joint_refinement/inference.json",
    "iteration10": ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json",
}
OUTPUT = Path(__file__).with_name("joint-weighting.json")
GROUPS = ("20260921_00", "20260921_16")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def entropy_effective_count(values: list[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    return math.exp(-sum((count / total) * math.log(count / total) for count in counts.values()))


def best_row(scan: dict) -> dict:
    rows = [row for row in scan["rows"] if row["fit"]["converged"]]
    return min(
        rows, key=lambda row: (row["fit"]["selection_objective"], abs(row["tau_s"]), row["tau_s"])
    )


def local_surface(iteration10: dict, group: str) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    rows = []
    # The final, 48.828 m lattice is the only surface used for curvature.
    for scan in iteration10["levels"][-1]["proposal_scans"]:
        if scan["group_id"] != group:
            continue
        chosen = best_row(scan)
        rows.append(
            {
                "east_km": float(scan["east_km_from_iteration9"]),
                "north_km": float(scan["north_km_from_iteration9"]),
                "loss": float(chosen["fit"]["selection_objective"]),
                "tau_s": float(chosen["tau_s"]),
                "tau_losses": [
                    float(row["fit"]["selection_objective"])
                    for row in scan["rows"]
                    if row["fit"]["converged"]
                ],
            }
        )
    # Use the closest 21 points to the group's own lattice minimum.  This bounds
    # the quadratic diagnostic to a local basin and does not consult any reference.
    minimum = min(rows, key=lambda row: row["loss"])
    rows.sort(
        key=lambda row: (
            (row["east_km"] - minimum["east_km"]) ** 2
            + (row["north_km"] - minimum["north_km"]) ** 2
        )
    )
    rows = rows[: min(21, len(rows))]
    return (
        np.array([[row["east_km"], row["north_km"]] for row in rows]),
        np.array([row["loss"] for row in rows]),
        rows,
    )


def quadratic_diagnostic(points: np.ndarray, losses: np.ndarray, rows: list[dict]) -> dict:
    # q(e,n) = b0 + b1 e + b2 n + 1/2 b3 e^2 + b4 e n + 1/2 b5 n^2.
    e, n = points[:, 0], points[:, 1]
    design = np.column_stack((np.ones_like(e), e, n, 0.5 * e * e, e * n, 0.5 * n * n))
    beta, _, _, _ = np.linalg.lstsq(design, losses, rcond=None)
    residual = losses - design @ beta
    residual_mad = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
    # Tau profiling changes are a second, directly observed nuisance-scale proxy.
    tau_gaps = []
    for row in rows:
        minimum = min(row["tau_losses"])
        tau_gaps.extend(value - minimum for value in row["tau_losses"] if value > minimum)
    tau_gap_median = float(np.median(tau_gaps)) if tau_gaps else 0.0
    hessian = np.array(((beta[3], beta[4]), (beta[4], beta[5])))
    eigenvalues = np.linalg.eigvalsh(hessian)
    # The scale is only for objective normalization.  The residual MAD is the
    # primary local roughness measure; the positive floor prevents a deterministic
    # grid fit from creating an infinite weight.
    scale = max(residual_mad, 1e-6)
    positive_definite = bool(np.all(eigenvalues > 0.0))
    normalized_hessian = hessian / scale
    information_area = (
        math.sqrt(float(np.linalg.det(normalized_hessian))) if positive_definite else 0.0
    )
    return {
        "surface_points": len(rows),
        "local_minimum": min(rows, key=lambda row: row["loss"]),
        "quadratic_hessian_loss_per_km2": hessian.tolist(),
        "hessian_eigenvalues_loss_per_km2": eigenvalues.tolist(),
        "positive_definite": positive_definite,
        "quadratic_residual_mad_loss": residual_mad,
        "normalization_scale_loss": scale,
        "tau_profile_gap_median_loss": tau_gap_median,
        "loss_range_loss": float(losses.max() - losses.min()),
        "information_area_per_km2": information_area,
    }


def source_diversity(iteration10: dict, group: str) -> dict:
    winner = iteration10["winner"]["best_exact_by_group"][group]
    associations = winner["track_associations"]
    candidates = [str(row["candidate_id"]) for row in associations]
    sessions = [str(row["session_id"]) for row in associations]
    tracks = [str(row["track_id"]) for row in associations]
    candidate_effective = entropy_effective_count(candidates)
    session_count = float(len(set(sessions)))
    # Candidate identity and session are different axes of repetition.  Their
    # geometric mean rewards coverage in both without treating 476 tracks as
    # independent evidence.
    source_coverage = min(math.sqrt(candidate_effective * session_count), float(len(set(tracks))))
    return {
        "association_count": len(associations),
        "distinct_candidate_count": len(set(candidates)),
        "candidate_entropy_effective_count": candidate_effective,
        "distinct_session_count": len(set(sessions)),
        "distinct_track_count": len(set(tracks)),
        "per_norad_rate_count": len(winner["exact_comparison"]["exact_rate_corrections_s_h"]),
        "source_coverage_effective_count": source_coverage,
    }


def exact_loss(finalist: dict, group: str) -> float:
    return float(
        finalist["best_exact_by_group"][group]["exact_comparison"][
            "exact_full_observation_capped_loss"
        ]
    )


def progression(artifacts: dict[str, dict]) -> list[dict]:
    rows = []
    prior = None
    for name, artifact in artifacts.items():
        winner = artifact["winner"]
        row = {
            "iteration": name,
            "latitude_deg": float(winner["latitude_deg"]),
            "longitude_deg": float(winner["longitude_deg"]),
            "balanced_exact_capped_loss": float(winner["balanced_exact_capped_loss"]),
            "exact_loss_by_group": {group: exact_loss(winner, group) for group in GROUPS},
            "exact_finalist_count": len(artifact["exact_finalists"]),
        }
        if prior is not None:
            north_km = (row["latitude_deg"] - prior["latitude_deg"]) * 111.32
            east_km = (
                (row["longitude_deg"] - prior["longitude_deg"])
                * 111.32
                * math.cos(math.radians(prior["latitude_deg"]))
            )
            row["movement_from_previous_km"] = math.hypot(east_km, north_km)
        rows.append(row)
        prior = row
    return rows


def main() -> None:
    artifacts = {name: json.loads(path.read_text()) for name, path in ITERATIONS.items()}
    if any(
        value.get("reference_used_for_fit") is not False or value.get("complete") is not True
        for value in artifacts.values()
    ):
        raise ValueError("all inputs must be complete reference-free inference artifacts")
    iteration10 = artifacts["iteration10"]
    group_metrics = {}
    raw_information = {}
    for group in GROUPS:
        points, losses, rows = local_surface(iteration10, group)
        curvature = quadratic_diagnostic(points, losses, rows)
        diversity = source_diversity(iteration10, group)
        # H/scale is the dimensionless local position information.  sqrt(D)
        # tempers the source contribution for possible within-session dependence.
        information = curvature["information_area_per_km2"] * math.sqrt(
            diversity["source_coverage_effective_count"]
        )
        group_metrics[group] = {
            "curvature_and_scale": curvature,
            "source_diversity": diversity,
            "source_tempered_information": information,
        }
        raw_information[group] = information
    total_information = sum(raw_information.values())
    weights = {group: raw_information[group] / total_information for group in GROUPS}

    finalists = []
    exact_minima = {
        group: min(exact_loss(row, group) for row in iteration10["exact_finalists"])
        for group in GROUPS
    }
    for row in iteration10["exact_finalists"]:
        loss_by_group = {group: exact_loss(row, group) for group in GROUPS}
        normalized_excess = {
            group: (loss_by_group[group] - exact_minima[group])
            / group_metrics[group]["curvature_and_scale"]["normalization_scale_loss"]
            for group in GROUPS
        }
        finalists.append(
            {
                "latitude_deg": row["latitude_deg"],
                "longitude_deg": row["longitude_deg"],
                "east_km_from_iteration9": row["east_km_from_iteration9"],
                "north_km_from_iteration9": row["north_km_from_iteration9"],
                "exact_loss_by_group": loss_by_group,
                "equal_group_exact_loss": row["balanced_exact_capped_loss"],
                "normalized_excess_by_group": normalized_excess,
                "source_tempered_normalized_score": sum(
                    weights[group] * normalized_excess[group] for group in GROUPS
                ),
            }
        )
    equal_ranked = sorted(
        finalists,
        key=lambda row: (
            row["equal_group_exact_loss"],
            row["north_km_from_iteration9"],
            row["east_km_from_iteration9"],
        ),
    )
    proposed_ranked = sorted(
        finalists,
        key=lambda row: (
            row["source_tempered_normalized_score"],
            row["north_km_from_iteration9"],
            row["east_km_from_iteration9"],
        ),
    )
    for rank, row in enumerate(equal_ranked, 1):
        row["equal_group_rank"] = rank
    for rank, row in enumerate(proposed_ranked, 1):
        row["proposed_rank"] = rank

    result = {
        "schema": "ds1-joint-weighting-diagnostic/v1",
        "complete": True,
        "reference_used_for_analysis_or_selection": False,
        "input_artifacts": {
            name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for name, path in ITERATIONS.items()
        },
        "analysis_scope": (
            "sealed iteration-8 to iteration-10 inference artifacts; iteration-10 finest "
            "proposal lattice and its eight existing exact finalists"
        ),
        "recommended_score": {
            "name": "source-tempered, curvature-and-scale-normalized exact score",
            "formula": "J(x) = sum_g w_g * (L_g(x) - min_c L_g(c)) / s_g",
            "weight_formula": (
                "w_g = [sqrt(D_g) * sqrt(det(H_g / s_g))] / sum_h [sqrt(D_h) * "
                "sqrt(det(H_h / s_h))]"
            ),
            "definitions": {
                "L_g": "existing exact capped loss for group g",
                "s_g": (
                    "local quadratic residual MAD of the group proposal surface, floored at "
                    "1e-6 loss"
                ),
                "H_g": (
                    "2x2 local quadratic Hessian of the tau-profiled group proposal objective "
                    "in east/north km"
                ),
                "D_g": (
                    "geometric mean of candidate entropy-effective count and distinct session "
                    "count, capped by distinct tracks, from sealed hard associations"
                ),
            },
            "weights": weights,
            "guardrails": [
                (
                    "derive s, H, and D on training inference before the exact finalist "
                    "selection; do not tune them against post-seal error"
                ),
                (
                    "use a predeclared local lattice with enough points for a positive-definite "
                    "quadratic diagnostic"
                ),
                (
                    "if a group Hessian is not positive definite or the fitted residual exceeds "
                    "its local loss range by a material fraction, retain it at a predeclared floor "
                    "weight or fall back to normalized equal weights"
                ),
                "do not treat this eight-finalist rerank as a fresh coordinate search",
            ],
        },
        "group_metrics": group_metrics,
        "iteration_progression": progression(artifacts),
        "existing_exact_finalist_rerank": proposed_ranked,
        "equal_group_winner": {
            key: equal_ranked[0][key]
            for key in (
                "latitude_deg",
                "longitude_deg",
                "equal_group_rank",
                "proposed_rank",
                "source_tempered_normalized_score",
            )
        },
        "proposed_winner": {
            key: proposed_ranked[0][key]
            for key in (
                "latitude_deg",
                "longitude_deg",
                "equal_group_rank",
                "proposed_rank",
                "source_tempered_normalized_score",
            )
        },
        "rerank_is_postfit_only": True,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "weights": weights,
                "equal_winner": result["equal_group_winner"],
                "proposed_winner": result["proposed_winner"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
