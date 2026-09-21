"""Evaluate a sealed exact-propagation identity/orbit quadrature cache.

The cache is deliberately numerical: catalogue and SGP4 code remain outside the
analyzer.  ``predicted_hz`` must contain exact Doppler for every shortlisted
candidate at every common Gaussian phase-rate node.  An optional full-catalogue
array performs the required corrected-model tail check at the sealed mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.identity_mixture import MixtureConfig
from leo.analysis.research.orbit_identity_mixture import (
    OrbitQuadratureConfig,
    omitted_signal_fraction,
    orbit_identity_statistics,
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(cache_path: Path, *, node_count: int, sigma_s_h: float) -> dict:
    data = dict(np.load(cache_path, allow_pickle=False))
    quadrature = OrbitQuadratureConfig(sigma_s_h, node_count)
    rates, weights = quadrature.nodes()
    cached_rates = np.asarray(data["phase_rate_nodes_s_h"], dtype=float)
    if not np.array_equal(cached_rates, rates):
        raise ValueError("cache nodes do not exactly match the frozen quadrature")
    episode = np.asarray(data["episode"], dtype=int)
    results = []
    tail = []
    for index in np.unique(episode):
        mask = episode == index
        predicted = data[f"predicted_hz_{index}"]
        visible = data[f"visible_{index}"].astype(bool)
        stats = orbit_identity_statistics(
            data["observed_hz"][mask],
            predicted,
            data["unassigned_residual_hz"][mask],
            data["segment"][mask],
            data["training"][mask].astype(bool),
            int(data["catalogue_size"][index]),
            node_weights=weights,
            visible=visible,
            config=MixtureConfig(),
        )
        results.append(
            {
                "episode": int(index),
                "train_log_evidence": stats["train_log_evidence"],
                "heldout_log_predictive": stats["heldout_log_predictive"],
                "candidate_posterior": np.asarray(stats["candidate_posterior"]).tolist(),
                "unassigned_posterior": stats["unassigned_posterior"],
            }
        )
        full_key = f"full_candidate_node_train_log_likelihood_{index}"
        if full_key in data:
            tail.append(
                omitted_signal_fraction(
                    data[full_key], data[f"full_candidate_kept_{index}"].astype(bool), weights
                )
            )
    return {
        "complete": True,
        "model_scope": (
            "independent per-episode orbit correction diagnostic; "
            "not shared-satellite joint inference"
        ),
        "strictly_causal_required_by_cache_contract": True,
        "heldout_used_for_fitting": False,
        "phase_rate_prior": {"mean_s_h": 0.0, "sigma_s_h": sigma_s_h},
        "quadrature": {
            "kind": "Gauss-Hermite",
            "node_count": node_count,
            "nodes_s_h": rates.tolist(),
            "weights": weights.tolist(),
        },
        "candidate_prior": "signal_prior / full causal catalogue size",
        "cache_digest": _digest(cache_path),
        "episodes": results,
        "full_catalogue_corrected_tail": None
        if not tail
        else {
            "episodes": len(tail),
            "maximum_omitted_signal_fraction": float(np.max(tail)),
            "p99_omitted_signal_fraction": float(np.quantile(tail, 0.99)),
            "episodes_above_1e-4": int(np.sum(np.asarray(tail) > 1e-4)),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node-count", type=int, default=7)
    parser.add_argument("--phase-rate-sigma-s-h", type=float, default=0.09176615913014215)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output path required")
    result = evaluate(args.cache, node_count=args.node_count, sigma_s_h=args.phase_rate_sigma_s_h)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
