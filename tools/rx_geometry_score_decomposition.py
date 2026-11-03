"""Decompose frozen held scores into count and conditional-frequency evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import NamedTuple

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.special import gammaln, logsumexp

from tools.rx_geometry_fit import lane_loglik, prepare, raw_features, signal_arrays
from tools.rx_geometry_likelihood import paired_log_likelihood

FloatArray = NDArray[np.float64]
ARM_DIMENSIONS = {"D": 3, "S": 6, "T": 8, "swap": 8, "reverse": 8}
CONTRASTS = (("T", "D"), ("S", "D"), ("T", "S"), ("T", "swap"), ("T", "reverse"))


class ScoreDecomposition(NamedTuple):
    """Sequential held scores under a posterior updated by full evidence only."""

    full_log_evidence: float
    count_log_evidence: float
    conditional_frequency_log_evidence: float
    full_window_log_scores: FloatArray
    count_window_log_scores: FloatArray
    conditional_frequency_window_log_scores: FloatArray
    reception_log_posterior: FloatArray
    held_log_posterior: FloatArray


def paired_count_log_likelihood(
    counts: ArrayLike,
    logits: ArrayLike,
    visibility: ArrayLike,
    lambdas: ArrayLike,
    period: float,
    *,
    latent_sd: float = 1.0,
    quadrature_order: int = 5,
) -> FloatArray:
    """Return the proper paired count PMF for every window and component.

    A uniform signal on the circle gives ``period * sum_j g(f_j) = n``.
    Converting the resulting unordered-set density to a count probability adds
    ``n log(period) - log(n!)`` for each receiver.
    """
    count_array = np.asarray(counts)
    logit_array = np.asarray(logits, dtype=float)
    if count_array.ndim != 2 or count_array.shape[1:] != (2,):
        raise ValueError("counts must have shape (windows, 2)")
    if (
        logit_array.ndim != 3
        or logit_array.shape[0] != count_array.shape[0]
        or logit_array.shape[2] != 2
    ):
        raise ValueError("logits must have shape (windows, components, 2)")
    components = logit_array.shape[1]
    uniform_signal_sums = np.broadcast_to(
        count_array[:, None, :], count_array.shape[:1] + (components, 2)
    )
    set_loglik = paired_log_likelihood(
        uniform_signal_sums,
        count_array,
        logit_array,
        visibility,
        lambdas,
        period,
        latent_sd=latent_sd,
        quadrature_order=quadrature_order,
    )
    measure = np.sum(count_array * np.log(period) - gammaln(count_array + 1), axis=1)
    return set_loglik + measure[:, None]


def decompose_sequence(
    logprior: ArrayLike,
    full_loglik: ArrayLike,
    count_loglik: ArrayLike,
    reception_mask: ArrayLike,
    held_mask: ArrayLike,
) -> ScoreDecomposition:
    """Score count and frequency pieces using the same full-evidence history."""
    prior = np.asarray(logprior, dtype=float)
    full = np.asarray(full_loglik, dtype=float)
    count = np.asarray(count_loglik, dtype=float)
    reception = np.asarray(reception_mask, dtype=bool)
    held = np.asarray(held_mask, dtype=bool)
    if prior.ndim != 1 or prior.size == 0:
        raise ValueError("logprior must be a nonempty one-dimensional array")
    if full.ndim != 2 or full.shape != count.shape or full.shape[1] != prior.size:
        raise ValueError("likelihood arrays must have shape (windows, components)")
    if reception.shape != (full.shape[0],) or held.shape != reception.shape:
        raise ValueError("masks must have shape (windows,)")
    if np.any(reception & held):
        raise ValueError("reception and held masks must be disjoint")
    if np.any(np.isnan(prior)) or np.any(np.isnan(full)) or np.any(np.isnan(count)):
        raise ValueError("log inputs may not contain NaN")
    normalizer = float(logsumexp(prior))
    if not np.isfinite(normalizer):
        raise ValueError("prior has zero total mass")
    posterior = prior - normalizer
    for row in full[reception]:
        updated = posterior + row
        evidence = float(logsumexp(updated))
        if not np.isfinite(evidence):
            raise ValueError("reception window has zero full predictive density")
        posterior = updated - evidence
    reception_posterior = posterior.copy()

    full_scores, count_scores = [], []
    for full_row, count_row in zip(full[held], count[held], strict=True):
        full_score = float(logsumexp(posterior + full_row))
        count_score = float(logsumexp(posterior + count_row))
        if not np.isfinite(full_score) or not np.isfinite(count_score):
            raise ValueError("held window has zero predictive density")
        full_scores.append(full_score)
        count_scores.append(count_score)
        # Both scores above use exactly the same incoming posterior.  Only the
        # complete candidate-set likelihood is then allowed to update history.
        posterior = posterior + full_row - full_score

    full_array = np.asarray(full_scores, dtype=float)
    count_array = np.asarray(count_scores, dtype=float)
    conditional_array = full_array - count_array
    return ScoreDecomposition(
        float(full_array.sum()),
        float(count_array.sum()),
        float(conditional_array.sum()),
        full_array,
        count_array,
        conditional_array,
        reception_posterior,
        posterior,
    )


def _finite_logs(values: FloatArray) -> list[float | None]:
    return [float(value) if np.isfinite(value) else None for value in values]


def evaluate_decomposition(lanes, beta, lambdas, center, scale, control=None):
    recordings: dict[str, dict] = {}
    lane_scores = []
    for lane in lanes:
        source = lane["source"]
        if source["recording_split"] != "evaluation":
            continue
        features = lane["x"]
        if control is not None:
            features = (raw_features(source, control)[0] - center) / scale
        logits = features[..., : len(beta)] @ beta
        full_loglik = lane_loglik(lane, beta, lambdas, x=features)
        count_loglik = paired_count_log_likelihood(
            lane["counts"], logits, lane["visible"], lambdas, source["alias_period_hz"]
        )
        score = decompose_sequence(
            lane["prior"],
            full_loglik,
            count_loglik,
            lane["roles"] == "reception",
            lane["roles"] == "held_frequency",
        )
        held_windows = len(score.full_window_log_scores)
        sid = source["lane"]["session_id"]
        record = recordings.setdefault(
            sid,
            {
                "held_windows": 0,
                "full_log_score": 0.0,
                "count_log_score": 0.0,
                "conditional_frequency_log_score": 0.0,
            },
        )
        record["held_windows"] += held_windows
        record["full_log_score"] += score.full_log_evidence
        record["count_log_score"] += score.count_log_evidence
        record["conditional_frequency_log_score"] += score.conditional_frequency_log_evidence
        lane_scores.append(
            {
                "lane": source["lane"],
                "held_windows": held_windows,
                "full_window_log_scores": score.full_window_log_scores.tolist(),
                "count_window_log_scores": score.count_window_log_scores.tolist(),
                "conditional_frequency_window_log_scores": (
                    score.conditional_frequency_window_log_scores.tolist()
                ),
                "reception_log_weights": _finite_logs(score.reception_log_posterior),
                "held_log_weights": _finite_logs(score.held_log_posterior),
            }
        )
    for record in recordings.values():
        windows = record["held_windows"]
        for metric in ("full", "count", "conditional_frequency"):
            record[f"{metric}_log_score_per_window"] = record[f"{metric}_log_score"] / windows
    return {
        "recordings": recordings,
        "lane_scores": lane_scores,
        "equal_record_mean": {
            metric: float(
                np.mean([row[f"{metric}_log_score_per_window"] for row in recordings.values()])
            )
            for metric in ("full", "count", "conditional_frequency")
        },
    }


def build_report(dataset: dict, results: dict, dataset_bytes: bytes, results_bytes: bytes) -> dict:
    if (
        results.get("schema") != "rx-geometry-association-pilot/v1"
        or results.get("status") != "complete"
    ):
        raise ValueError("results are not a complete frozen association fit")
    dataset_digest = hashlib.sha256(dataset_bytes).hexdigest()
    if results.get("dataset_sha256") != dataset_digest:
        raise ValueError("results-to-dataset hash mismatch")
    lanes, prepared_center, prepared_scale = prepare(dataset)
    center = np.asarray(results["feature_center"], dtype=float)
    scale = np.asarray(results["feature_scale"], dtype=float)
    if not np.array_equal(center, prepared_center) or not np.array_equal(scale, prepared_scale):
        raise ValueError("frozen feature scaler does not match prepared dataset")
    signal_arrays(lanes, float(results["sigma_hz"]))
    lambdas = np.asarray(results["clutter_intensities"], dtype=float)
    evaluations = {}
    for arm, dimension in ARM_DIMENSIONS.items():
        fit_name = arm if arm in ("D", "S", "T") else "T"
        beta = np.asarray(results["fits"][fit_name]["parameters"], dtype=float)
        if beta.shape != (dimension,):
            raise ValueError(f"unexpected coefficient dimension for {arm}")
        control = arm if arm in ("swap", "reverse") else None
        evaluations[arm] = evaluate_decomposition(lanes, beta, lambdas, center, scale, control)

    denominators = [
        {sid: row["held_windows"] for sid, row in evaluation["recordings"].items()}
        for evaluation in evaluations.values()
    ]
    if any(item != denominators[0] for item in denominators[1:]):
        raise ValueError("arm/control held-window denominators differ")
    contrasts = {}
    for left, right in CONTRASTS:
        contrasts[f"{left}-{right}"] = {
            sid: {
                metric: evaluations[left]["recordings"][sid][f"{metric}_log_score_per_window"]
                - evaluations[right]["recordings"][sid][f"{metric}_log_score_per_window"]
                for metric in ("full", "count", "conditional_frequency")
            }
            for sid in evaluations[left]["recordings"]
        }
    return {
        "schema": "rx-geometry-score-decomposition/v1",
        "status": "complete",
        "source_sha256": {
            "dataset": dataset_digest,
            "results": hashlib.sha256(results_bytes).hexdigest(),
        },
        "method": "Count and conditional-frequency scores share the full-evidence posterior "
        "before each held window; only full evidence updates history.",
        "evaluations": evaluations,
        "contrasts_per_record": contrasts,
        "contrasts_equal_record_mean": {
            contrast: {
                metric: float(np.mean([row[metric] for row in records.values()]))
                for metric in ("full", "count", "conditional_frequency")
            }
            for contrast, records in contrasts.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_bytes = args.dataset.read_bytes()
    results_bytes = args.results.read_bytes()
    report = build_report(
        json.loads(dataset_bytes), json.loads(results_bytes), dataset_bytes, results_bytes
    )
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
