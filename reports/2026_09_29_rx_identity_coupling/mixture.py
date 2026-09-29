"""Normalized independent/shared candidate assignment with explicit background."""

import math

import numpy as np


def logsum(values):
    return float(np.logaddexp.reduce(np.asarray(values, float)))


def pair_density(a, b, coupling, background=0.2):
    if not 0 <= coupling <= 1 or not 0 <= background <= 1:
        raise ValueError("Probabilities must lie in [0,1]")
    if a["snapshot"] != b["snapshot"]:
        raise ValueError("Different candidate namespaces")
    arrays = []
    for item in (a, b):
        ids, values = np.asarray(item["ids"]), np.asarray(item["signal"], float)
        if (
            ids.ndim != 1
            or not np.issubdtype(ids.dtype, np.integer)
            or len(ids) == 0
            or len(set(ids.tolist())) != len(ids)
            or values.shape != ids.shape
            or np.isnan(values).any()
            or np.isposinf(values).any()
            or math.isnan(item["background"])
            or item["background"] == math.inf
        ):
            raise ValueError("Invalid candidate densities")
        arrays.append((ids, values))
    (ia, la), (ib, lb) = arrays
    sa, sb = logsum(la) - math.log(len(la)), logsum(lb) - math.log(len(lb))
    ids, i, j = np.intersect1d(ia, ib, return_indices=True)
    independent = sa + sb
    shared = logsum(la[i] + lb[j]) - math.log(len(ids)) if len(ids) else -math.inf
    q = background
    masses = [
        (1 - q) ** 2 * (1 - coupling),
        (1 - q) ** 2 * coupling if len(ids) else 0,
        (1 - q) * q,
        q * (1 - q),
        q * q + ((1 - q) ** 2 * coupling if not len(ids) else 0),
    ]
    likelihoods = [
        independent,
        shared,
        sa + b["background"],
        a["background"] + sb,
        a["background"] + b["background"],
    ]
    terms = [math.log(m) + v if m else -math.inf for m, v in zip(masses, likelihoods, strict=True)]
    return {
        "log_density": logsum(terms),
        "prior_masses": masses,
        "common_candidates": len(ids),
        "shared_log_density": shared if len(ids) else None,
    }


def single_density(item, background=0.2):
    signal = logsum(item["signal"]) - math.log(len(item["signal"]))
    return logsum([math.log1p(-background) + signal, math.log(background) + item["background"]])


def evaluate_pairs(tracks, pairs, coupling):
    """Pair each track at most once; retain unpaired tracks independently."""
    used, rows = set(), []
    score = 0.0
    for a, b in pairs:
        if a == b or a in used or b in used or a not in tracks or b not in tracks:
            raise ValueError("Invalid or duplicated paired track")
        used.update((a, b))
        result = pair_density(tracks[a], tracks[b], coupling)
        score += result["log_density"]
        rows.append({"left": a, "right": b, **result})
    for key in sorted(tracks.keys() - used):
        score += single_density(tracks[key])
    return {
        "score": score,
        "pairs": rows,
        "paired_tracks": len(used),
        "unpaired_tracks": len(tracks) - len(used),
    }
