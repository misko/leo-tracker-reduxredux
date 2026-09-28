"""Lag-selected repeated-visit sequence comparison with disjoint chronological evaluation."""

import csv
import json
from collections import defaultdict
from itertools import combinations

import numpy as np
from phase_model import CLUSTER, OUT


def aligned(a, b, lag, lower, upper):
    return [
        (a[f], b[f + lag])
        for f in sorted(a)
        if lower <= f < upper and lower <= f + lag < upper and f + lag in b
    ]


def main():
    groups = defaultdict(dict)
    with (OUT / "phase_indices.csv").open() as stream:
        for r in csv.DictReader(stream):
            if r["signal"] != "UT-ref":
                groups[r["signal"]][int(r["frame"])] = int(r["phase_index"])
    with (CLUSTER / "metadata_signals.csv").open() as stream:
        metadata = {r["signal"]: r for r in csv.DictReader(stream)}
    pairs = []
    rng = np.random.default_rng(20260928)
    for a, b in combinations(sorted(groups), 2):
        if min(len(groups[a]), len(groups[b])) < 10:
            continue
        trials = []
        for lag in range(-15, 16):
            observed = aligned(groups[a], groups[b], lag, 0, 44)
            if len(observed) >= 5:
                trials.append(
                    (
                        sum(x == y for x, y in observed) / len(observed),
                        len(observed),
                        -abs(lag),
                        lag,
                    )
                )
        if not trials:
            continue
        rate, train_n, _, lag = max(trials)
        evaluation = aligned(groups[a], groups[b], lag, 44, 90)
        if len(evaluation) < 5:
            continue
        observed = sum(x == y for x, y in evaluation) / len(evaluation)
        x, y = np.array(evaluation).T
        controls = [np.mean(x == rng.permutation(y)) for _ in range(499)]
        ida, idb = [metadata[s]["known_conditional_norad"] for s in [a, b]]
        pairs.append(
            dict(
                a=a,
                b=b,
                same_prior_identity=ida == idb if ida and idb else None,
                same_session=metadata[a]["session"] == metadata[b]["session"],
                selected_lag=lag,
                discovery_matches_fraction=rate,
                discovery_n=train_n,
                evaluation_matches_fraction=observed,
                evaluation_n=len(evaluation),
                shuffled_mean=float(np.mean(controls)),
                shuffle_p=(1 + sum(v >= observed for v in controls)) / 500,
            )
        )
    summary = []
    for identity in [True, False, None]:
        subset = [r for r in pairs if r["same_prior_identity"] == identity]
        n = sum(r["evaluation_n"] for r in subset)
        summary.append(
            dict(
                same_prior_identity=identity,
                pairs=len(subset),
                compared_frame_pairs=n,
                match_fraction=sum(
                    r["evaluation_n"] * r["evaluation_matches_fraction"] for r in subset
                )
                / n
                if n
                else None,
                shuffled_fraction=sum(r["evaluation_n"] * r["shuffled_mean"] for r in subset) / n
                if n
                else None,
            )
        )
    result = dict(
        pairs=pairs,
        summary=summary,
        limitations="Lags -15..15 are selected only on frames <44, evaluated on frames >=44. "
        "These are relative sequence alignments, not UTC or RF-phase alignment. "
        "Missing frames remain missing. Paired comparisons share visits and are "
        "not independent. Shuffle values are exploratory controls, not semantic proof.",
    )
    (OUT / "sequence_comparisons.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
