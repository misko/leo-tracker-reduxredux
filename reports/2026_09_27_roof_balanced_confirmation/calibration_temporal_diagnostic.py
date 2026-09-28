"""Calibration-only OOF diagnostics for repeated detection outcomes.

This is descriptive.  It neither fits a model nor consumes geographic errors.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import mixture_calibration_inputs as inputs
import mixture_reception_core as core
import run_mixture_polished_full as full_runner


HERE = Path(__file__).resolve().parent
ARMS = ("M0", "mean", "mixture")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def detection_predictions(theta, track, layout):
    """Return candidate and prior-marginal detection probabilities."""
    parameter = np.asarray(theta, float)
    design = np.asarray(track.detection_design, float)
    weights = np.exp(np.asarray(track.log_weights, float))
    if parameter.shape != (layout.size,) or design.ndim != 3:
        raise ValueError("invalid parameter/design shape")
    logits = np.einsum("knp,p->kn", design, parameter[:layout.detection_size])
    candidate = 1. / (1. + np.exp(-np.clip(logits, -40., 40.)))
    marginal = weights @ candidate
    if (not np.all(np.isfinite(candidate)) or not np.all(np.isfinite(marginal)) or
            np.any(marginal <= 0) or np.any(marginal >= 1)):
        raise ValueError("invalid detection probabilities")
    return candidate, marginal


def summarize_tracks(records):
    """Summarize OOF residual dependence, allowing shared candidate identity."""
    adjacent_product_sum = 0.
    adjacent_excess_sum = 0.
    adjacent_scale_sum = 0.
    gaps = []
    cluster_numerator = 0.
    cluster_denominator = 0.
    rows = pairs = 0
    for record in records:
        y = np.asarray(record["matched"], float)
        p = np.asarray(record["marginal_probability"], float)
        candidate = np.asarray(record["candidate_probability"], float)
        weights = np.asarray(record["weights"], float)
        times = np.asarray(record["times_s"], float)
        if (y.ndim != 1 or p.shape != y.shape or times.shape != y.shape or
                candidate.shape[1:] != y.shape or candidate.shape[0] != len(weights) or
                not np.isclose(weights.sum(), 1., atol=1e-10, rtol=0)):
            raise ValueError("invalid residual record")
        order = np.argsort(times, kind="stable")
        y, p, times, candidate = y[order], p[order], times[order], candidate[:, order]
        residual = y - p
        conditional_variance = np.sum(
            weights[:, None] * candidate * (1. - candidate), axis=0)
        candidate_sum = candidate.sum(axis=1)
        expected_cluster_variance = (conditional_variance.sum() +
            np.sum(weights * (candidate_sum - np.sum(weights * candidate_sum)) ** 2))
        cluster_numerator += float(residual.sum() ** 2)
        cluster_denominator += float(expected_cluster_variance)
        rows += len(y)
        for left in range(len(y) - 1):
            right = left + 1
            scale = math.sqrt(p[left] * (1-p[left]) * p[right] * (1-p[right]))
            model_covariance = float(np.sum(weights *
                (candidate[:, left] - p[left]) * (candidate[:, right] - p[right])))
            product = float(residual[left] * residual[right])
            adjacent_product_sum += product
            adjacent_excess_sum += product - model_covariance
            adjacent_scale_sum += scale
            gaps.append(float(times[right] - times[left]))
            pairs += 1
    if not rows or not pairs or cluster_denominator <= 0 or adjacent_scale_sum <= 0:
        raise ValueError("diagnostic requires rows, adjacent pairs, and positive variance")
    return {
        "tracks": len(records), "rows": rows, "adjacent_pairs": pairs,
        "adjacent_raw_standardized_covariance_ratio": adjacent_product_sum / adjacent_scale_sum,
        "adjacent_identity_adjusted_standardized_covariance_ratio": (
            adjacent_excess_sum / adjacent_scale_sum),
        "track_residual_sum_dispersion_ratio": cluster_numerator / cluster_denominator,
        "adjacent_gap_seconds": {
            "median": float(np.median(gaps)), "p90": float(np.quantile(gaps, .9)),
            "minimum": float(np.min(gaps)), "maximum": float(np.max(gaps))},
    }


def run():
    tracks, receipt = inputs.load_joined()
    raw_rows = json.loads((inputs.DIRECTION / "model_rows.json").read_text())
    timestamps = {(r["session_id"], r["track_id"], r["observation_id"]):
                  int(r["observation_utc_ns"]) / 1e9 for r in raw_rows}
    source_paths = {
        "model_rows.json": sha256(inputs.DIRECTION / "model_rows.json"),
        "calibration_directions_data.json": sha256(HERE / "calibration_directions_data.json"),
        "mixture_calibration_inputs.py": sha256(HERE / "mixture_calibration_inputs.py"),
        "mixture_reception_core.py": sha256(HERE / "mixture_reception_core.py"),
        "calibration_temporal_diagnostic.py": sha256(Path(__file__).resolve()),
    }
    records = {arm: [] for arm in ARMS}
    fold_counts = {}
    for session in receipt["sessions"]:
        path = HERE / f"mixture-calibration-polished-fold-{session}.json"
        artifact = json.loads(path.read_text()); source_paths[path.name] = sha256(path)
        held = tuple(t for t in tracks if t.session_id == session)
        train = tuple(t for t in tracks if t.session_id != session)
        schema = inputs.fit_schema(train)
        if (artifact.get("held_session") != session or
                artifact.get("feature_schema") != full_runner.json_value(asdict(schema)) or
                not artifact.get("all_models_converged") or set(artifact.get("models", {})) != set(ARMS)):
            raise ValueError(f"invalid polished LOSO artifact for {session}")
        fold_counts[session] = {"tracks": len(held), "rows": sum(len(t.rows) for t in held)}
        for arm in ARMS:
            built, layout, _names = inputs.build_arm(held, schema, arm, core)
            model = artifact["models"][arm]
            if not model.get("polish", {}).get("accepted"):
                raise ValueError(f"unaccepted {arm} fold model")
            theta = model["polish"]["theta"]
            for joined, tensor in zip(held, built, strict=True):
                candidate, marginal = detection_predictions(theta, tensor, layout)
                records[arm].append({
                    "matched": tensor.matched, "marginal_probability": marginal,
                    "candidate_probability": candidate,
                    "weights": np.exp(tensor.log_weights),
                    "times_s": [timestamps[(joined.session_id, joined.track_id,
                                            row.observation_id)] for row in joined.rows],
                })
    output = {
        "scope": "calibration_only_conditional_loso_detection_temporal_diagnostic",
        "estimand": {
            "adjacent_raw": "sum adjacent residual products divided by sum Bernoulli standard-deviation products",
            "adjacent_identity_adjusted": "raw product minus covariance implied by one frequency-prior candidate shared by the track, with the same aggregate denominator",
            "track_dispersion": "sum squared track residual sums divided by their model-implied variance",
        },
        "caveats": [
            "Candidate IDs are frequency-model associations, not decoded satellite identities.",
            "Frequency candidate priors were estimated using all six calibration sessions; only reception coefficients are leave-one-session-out.",
            "Adjacent rows are ordered by reception timestamp and can differ in receiver/channel; this is not a pure stationary time-series estimand.",
            "Ratios are excluded because conditioning on matched reception and shared identity requires a distinct joint posterior diagnostic.",
            "No reference distribution or cluster bootstrap is asserted; values are descriptive misspecification diagnostics.",
        ],
        "fold_counts": fold_counts,
        "arms": {arm: summarize_tracks(records[arm]) for arm in ARMS},
        "source_hashes": source_paths,
    }
    target = HERE / "calibration_temporal_diagnostic.json"
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return output


if __name__ == "__main__":
    run()
