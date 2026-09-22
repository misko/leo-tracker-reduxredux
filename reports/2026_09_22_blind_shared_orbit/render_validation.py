#!/usr/bin/env python3
"""Render a sealed blind shared-orbit validation without influencing its fit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCHEMA = "blind-shared-orbit-six-scan-validation/v1"
EXCLUDED_COARSE_MARKER = "blind-shared-orbit-coarse-v1-20260922"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_sealed(path: Path, coarse_path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text())
    if document.get("schema") != SCHEMA or document.get("state") not in {
        "complete",
        "insufficient",
    }:
        raise ValueError("validation is not a supported sealed terminal document")
    claimed = document.get("seal_sha256")
    unsealed = {key: value for key, value in document.items() if key != "seal_sha256"}
    if claimed != _digest_value(unsealed):
        raise ValueError("validation seal does not match the document")
    if EXCLUDED_COARSE_MARKER in str(coarse_path):
        raise ValueError("the randomized coarse-v1 acquisition is excluded")
    if document["provenance"]["coarse_result_sha256"] != _digest_file(coarse_path):
        raise ValueError("coarse acquisition digest differs from sealed provenance")
    if document.get("truth_accessed") is not False:
        raise ValueError("fit document must declare truth_accessed=false")
    return document


def _episodes(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["episode_id"]: row for row in result["shared_fit"]["episodes"]}


def _horizontal_error_m(lat: float, lon: float, ref_lat: float, ref_lon: float) -> float:
    radius_m = 6_371_008.8
    phi1, phi2 = map(math.radians, (lat, ref_lat))
    dphi = phi2 - phi1
    dlambda = math.radians(ref_lon - lon)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_m * math.asin(min(1.0, math.sqrt(a)))


def _predictive_plot(document: dict[str, Any], output: Path) -> dict[str, Any]:
    nominal_result = document.get("selected_nominal_result")
    if not isinstance(nominal_result, dict):
        raise ValueError("selected_nominal_result is required for matched held-out comparison")
    nominal = _episodes(nominal_result)
    shared = _episodes(document["selected_shared_result"])
    if set(nominal) != set(shared):
        raise ValueError("nominal and shared held-out episode support differs")
    ids = sorted(nominal)
    nominal_score = np.asarray([nominal[key]["heldout_log_predictive"] for key in ids])
    shared_score = np.asarray([shared[key]["heldout_log_predictive"] for key in ids])
    if not np.all(np.isfinite(nominal_score)) or not np.all(np.isfinite(shared_score)):
        raise ValueError("held-out predictive scores must be finite")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].scatter(nominal_score, shared_score, s=14, alpha=0.65)
    low = float(min(nominal_score.min(), shared_score.min()))
    high = float(max(nominal_score.max(), shared_score.max()))
    axes[0].plot([low, high], [low, high], color="0.35", linestyle="--", linewidth=1)
    axes[0].set(
        xlabel="Nominal held-out log predictive", ylabel="Shared-orbit held-out log predictive"
    )
    delta = shared_score - nominal_score
    axes[1].hist(delta, bins=min(24, max(6, int(math.sqrt(len(delta))))), color="#35618f")
    axes[1].axvline(0, color="0.25", linestyle="--", linewidth=1)
    axes[1].set(xlabel="Shared − nominal held-out log predictive", ylabel="Episodes")
    fig.suptitle("Matched held-out predictive comparison")
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return {
        "episode_count": len(ids),
        "nominal_sum": float(nominal_score.sum()),
        "shared_sum": float(shared_score.sum()),
        "delta_sum": float(delta.sum()),
        "shared_better_episode_count": int(np.count_nonzero(delta > 0)),
    }


def _branch_plot(
    document: dict[str, Any], output: Path, reference: tuple[float, float] | None
) -> list[dict[str, Any]]:
    rows = []
    # nominal-local rows disable shared-rate optimization, so their rate-zero
    # objective is not comparable to the shared-search trace colour scale.
    for item in document["outer_evaluations"]:
        if item["branch_id"] == "nominal-local":
            continue
        row = {
            "branch_id": item["branch_id"],
            "latitude_deg": float(item["latitude_deg"]),
            "longitude_deg": float(item["longitude_deg"]),
            "shared_objective": float(item["matched_shared_negative_log_posterior"]),
        }
        if reference is not None:
            row["reference_error_m"] = _horizontal_error_m(
                row["latitude_deg"], row["longitude_deg"], *reference
            )
        rows.append(row)
    score = np.asarray([item["shared_objective"] for item in rows])
    fig, ax = plt.subplots(figsize=(8, 5.5), constrained_layout=True)
    points = ax.scatter(
        [item["longitude_deg"] for item in rows],
        [item["latitude_deg"] for item in rows],
        c=score - score.min(),
        cmap="viridis_r",
        s=48,
    )
    selected = document["selected_shared"]
    ax.scatter(
        selected["longitude_deg"],
        selected["latitude_deg"],
        marker="*",
        s=190,
        label="Selected shared",
    )
    nominal = document["selected_nominal"]
    ax.scatter(
        nominal["longitude_deg"],
        nominal["latitude_deg"],
        marker="D",
        s=75,
        facecolors="none",
        edgecolors="black",
        label="Selected nominal",
    )
    if reference is not None:
        ax.scatter(
            reference[1], reference[0], marker="x", s=100, color="red", label="Evaluation reference"
        )
    ax.set(
        xlabel="Longitude (degrees)",
        ylabel="Latitude (degrees)",
        title="Shared-search trace (not confidence bounds)",
    )
    ax.legend()
    fig.colorbar(points, ax=ax, label="Shared training objective above evaluated minimum")
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return rows


def _rate_audit_plot(document: dict[str, Any], output: Path) -> dict[str, Any]:
    result = document["selected_shared_result"]
    rates = {int(k): float(v) for k, v in result["rate_corrections_s_h"].items()}
    recurrence = {int(k): int(v) for k, v in result["recurrent_norad_episode_count"].items()}
    recurrent = sorted(
        (n, recurrence.get(n, 0), rate) for n, rate in rates.items() if recurrence.get(n, 0) > 1
    )
    high_weight_counts: dict[int, int] = {}
    for episode in result["shared_fit"]["episodes"]:
        for norad, weight in zip(
            episode.get("candidate_norad", ()),
            episode.get("candidate_posterior", ()),
            strict=True,
        ):
            if float(weight) >= 0.5:
                number = int(norad)
                high_weight_counts[number] = high_weight_counts.get(number, 0) + 1
    recurrent_high_weight = sorted(
        (norad, count, rates.get(norad)) for norad, count in high_weight_counts.items() if count > 1
    )
    audits = result["exact_replay_audits"]
    maximum = np.asarray(
        [row["maximum_error_hz"] for row in audits if row.get("state") == "complete"]
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    if recurrent:
        axes[0].scatter([x[1] for x in recurrent], [x[2] for x in recurrent], s=24)
    axes[0].axhline(0, color="0.3", linewidth=1)
    axes[0].set(
        xlabel="Episodes retaining NORAD",
        ylabel="Shared phase rate (s/hour)",
        title="Recurrent candidate corrections",
    )
    if len(maximum):
        axes[1].hist(maximum, bins=min(24, max(6, int(math.sqrt(len(maximum))))), color="#b05b3b")
    axes[1].set(
        xlabel="Exact replay maximum error (Hz)", ylabel="Episodes", title="Approximation audit"
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)
    threshold = float(document["protocol"]["configuration"]["exact_audit_maximum_error_hz"])
    return {
        "fitted_norad_count": len(rates),
        "recurrent_norad_count": len(recurrent),
        "recurrent": [{"norad": n, "episode_count": c, "rate_s_h": r} for n, c, r in recurrent],
        "high_weight_definition": "candidate_posterior>=0.5 within an episode",
        "recurrent_high_weight_norad_count": len(recurrent_high_weight),
        "recurrent_high_weight": [
            {"norad": n, "episode_count": c, "rate_s_h": r} for n, c, r in recurrent_high_weight
        ],
        "exact_audit_complete_count": int(len(maximum)),
        "exact_audit_maximum_error_hz": float(maximum.max()) if len(maximum) else None,
        "exact_audit_threshold_hz": threshold,
        "exact_audit_pass": bool(
            len(maximum) and len(maximum) == len(audits) and maximum.max() <= threshold
        ),
    }


def _transfer_summary(document: dict[str, Any]) -> dict[str, Any]:
    transfer = document["transfer_evaluation"]
    audits = transfer.get("exact_replay_audits", ())
    complete = [
        float(item["maximum_error_hz"])
        for item in audits
        if item.get("state") == "complete" and item.get("maximum_error_hz") is not None
    ]
    fit = transfer.get("shared_fit", {})
    scores = transfer.get("outer_position_scores", {})
    return {
        "episode_count": len(fit.get("episodes", ())),
        "heldout_log_predictive_sum": sum(
            float(item["heldout_log_predictive"]) for item in fit.get("episodes", ())
        ),
        "matched_nominal_negative_log_posterior": scores.get(
            "matched_shortlist_nominal_negative_log_posterior"
        ),
        "matched_shared_negative_log_posterior": scores.get(
            "matched_shortlist_shared_negative_log_posterior"
        ),
        "inner_converged": fit.get("converged"),
        "inner_message": fit.get("message"),
        "exact_audit_complete_count": len(complete),
        "exact_audit_maximum_error_hz": max(complete) if complete else None,
        "corrected_support_certified": transfer.get("corrected_support_certified"),
        "corrected_support_status": transfer.get("corrected_support_status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed-result", type=Path, required=True)
    parser.add_argument("--coarse-result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-latitude-deg", type=float)
    parser.add_argument("--reference-longitude-deg", type=float)
    args = parser.parse_args()
    if (args.reference_latitude_deg is None) != (args.reference_longitude_deg is None):
        parser.error("both evaluation reference coordinates are required together")
    document = _load_sealed(args.sealed_result, args.coarse_result)
    # Truth is accepted only after the fit seal and acquisition provenance pass above.
    reference = (
        None
        if args.reference_latitude_deg is None
        else (args.reference_latitude_deg, args.reference_longitude_deg)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictive = _predictive_plot(document, args.output_dir / "heldout-predictive-comparison.png")
    branches = _branch_plot(document, args.output_dir / "spatial-branch-evaluation.png", reference)
    rates = _rate_audit_plot(document, args.output_dir / "rate-recurrence-exact-audit.png")
    selected_errors = None
    if reference is not None:
        selected_errors = {
            "nominal_horizontal_error_m": _horizontal_error_m(
                document["selected_nominal"]["latitude_deg"],
                document["selected_nominal"]["longitude_deg"],
                *reference,
            ),
            "shared_horizontal_error_m": _horizontal_error_m(
                document["selected_shared"]["latitude_deg"],
                document["selected_shared"]["longitude_deg"],
                *reference,
            ),
            "interpretation": "post-seal diagnostic; reference did not select either estimate",
        }
    summary = {
        "schema": "blind-shared-orbit-rendered-summary/v1",
        "source_seal_sha256": document["seal_sha256"],
        "source_file_sha256": _digest_file(args.sealed_result),
        "coarse_result_sha256": _digest_file(args.coarse_result),
        "truth_accessed_during_fit": document["truth_accessed"],
        "sealed_runner_state": document["state"],
        "scientific_qualification": (
            "complete"
            if document["state"] == "complete" and rates["exact_audit_pass"]
            else "insufficient"
        ),
        "causal_scope": (
            "TLE snapshots and element epochs are causal to each capture and target truth is "
            "excluded from fitting; the fixed research hyperparameters were applied "
            "retrospectively and are not certified as learned before this archived cohort"
        ),
        "evaluation_reference": None
        if reference is None
        else {
            "latitude_deg": reference[0],
            "longitude_deg": reference[1],
            "source": "user-provided-report-reference-after-seal",
        },
        "accounting": document["accounting"],
        "protocol": document["protocol"],
        "selected_nominal": document["selected_nominal"],
        "selected_shared": document["selected_shared"],
        "selected_reference_errors": selected_errors,
        "outer_optimizer": document.get("outer_optimizer"),
        "inner_optimizer": {
            "nominal": document["selected_nominal_result"]["shared_fit"].get("converged"),
            "nominal_message": document["selected_nominal_result"]["shared_fit"].get("message"),
            "shared": document["selected_shared_result"]["shared_fit"].get("converged"),
            "shared_message": document["selected_shared_result"]["shared_fit"].get("message"),
        },
        "predictive": predictive,
        "branches": branches,
        "rate_and_audit": rates,
        "transfer_evaluation": _transfer_summary(document),
        "limitations": document["limitations"],
    }
    summary["summary_sha256"] = _digest_value(summary)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
