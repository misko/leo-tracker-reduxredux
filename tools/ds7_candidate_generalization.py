"""Conditional candidate discrimination with alternatives selected only by training."""

from __future__ import annotations

import numpy as np
from scipy.special import logsumexp


def compare_candidates(candidate_ids, training_scores, held_scores):
    ids = np.asarray(candidate_ids)
    train, held = np.asarray(training_scores, dtype=float), np.asarray(held_scores, dtype=float)
    if (
        ids.ndim != 1
        or train.shape != ids.shape
        or held.shape != ids.shape
        or len(set(ids.tolist())) != len(ids)
        or np.isnan(train).any()
        or np.isposinf(train).any()
        or not np.isfinite(held).all()
    ):
        raise ValueError("unique IDs and aligned finite held / valid training scores required")
    eligible = np.flatnonzero(np.isfinite(train))
    if not len(eligible):
        raise ValueError("no visible candidate")
    # Catalogue number resolves exact training ties without consulting held data.
    ranked = sorted(eligible, key=lambda i: (-train[i], int(ids[i])))
    winner = ranked[0]
    normal = float(logsumexp(train))
    weights = np.exp(train - normal)
    full = float(logsumexp(train + held) - normal)
    row = {
        "map_catalogue_id": int(ids[winner]),
        "map_probability": float(weights[winner]),
        "effective_candidates": float(1 / (weights @ weights)),
        "visible_candidates": len(ranked),
        "map_held_log_score": float(held[winner]),
        "full_held_log_score": full,
        "runner_up_catalogue_id": None,
        "runner_up_held_minus_map": None,
        "training_gap": None,
        "alternative_mixture_held_minus_full": None,
        "candidate_ids": ids.tolist(),
        "weights": weights.tolist(),
        "held_scores": held.tolist(),
    }
    if len(ranked) > 1:
        runner = ranked[1]
        rest = np.asarray(ranked[1:])
        alternative = float(logsumexp(train[rest] + held[rest]) - logsumexp(train[rest]))
        row.update(
            runner_up_catalogue_id=int(ids[runner]),
            runner_up_held_minus_map=float(held[runner] - held[winner]),
            training_gap=float(train[winner] - train[runner]),
            alternative_mixture_held_minus_full=alternative - full,
        )
    return row
