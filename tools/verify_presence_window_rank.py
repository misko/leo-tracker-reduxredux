"""Strict numerical/accounting comparison for saved-IQ ARM screen replays."""

from __future__ import annotations

import math

import numpy as np

BINS = (512, 1024, 2048, 4096, 8192)
TIMINGS = ("fold_cpu_ms", "correlation_cpu_ms", "total_cpu_ms", "total_wall_ms")


def _key(row):
    rate, edge, counter = row["rate_hz"], row["edge"], row["counter"]
    if (
        type(rate) is not int
        or rate not in (2500000, 5000000)
        or type(edge) is not int
        or edge not in (0, 1)
        or type(counter) is not str
        or not counter.isdecimal()
        or counter != str(int(counter))
        or not 0 <= int(counter) <= 2**64 - 1 - rate // 50 * 6
        or type(row["bins"]) is not int
        or row["bins"] not in BINS
        or type(row["iteration"]) is not int
        or not 0 <= row["iteration"] < 20
    ):
        raise ValueError("invalid replay identity")
    if (
        len(row["scores"]) != 6
        or len(row["order"]) != 6
        or len(row["projected_epoch_samples"]) != 6
        or any(
            type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1.00001
            for x in row["scores"]
        )
        or any(type(x) is not int for x in row["order"])
        or row["order"] != sorted(range(6), key=lambda k: -row["scores"][k])
        or any(
            type(x) is not int or not 0 <= x < round(rate / 750)
            for x in row["projected_epoch_samples"]
        )
        or any(
            type(row[k]) not in (int, float) or not math.isfinite(row[k]) or row[k] < 0
            for k in TIMINGS
        )
    ):
        raise ValueError("invalid replay numerical output")
    return rate, edge, counter, row["bins"], row["iteration"]


def verify(desktop, arm, specifications):
    """Tolerances frozen in independent FP64-oracle tests before ARM output."""
    identities = [(r["rate_hz"], r["edge"], r["counter"]) for r in specifications]
    if not identities or len(set(identities)) != len(identities):
        raise ValueError("nonduplicate source inventory required")
    expected = {
        (*identity, bins, iteration)
        for identity in identities
        for bins in BINS
        for iteration in range(20)
    }
    indexed = []
    for records in (desktop, arm):
        pairs = [(_key(r), r) for r in records]
        mapping = dict(pairs)
        if len(mapping) != len(records) or set(mapping) != expected:
            raise ValueError("missing, duplicated, or unexpected replay")
        indexed.append(mapping)
    largest_difference = 0.0
    for key, actual in indexed[1].items():
        reference = indexed[0][key]
        difference = np.abs(np.array(actual["scores"]) - reference["scores"])
        largest_difference = max(largest_difference, float(np.max(difference)))
        if (
            not np.allclose(actual["scores"], reference["scores"], rtol=2e-6, atol=2e-7)
            or actual["order"] != reference["order"]
            or actual["projected_epoch_samples"] != reference["projected_epoch_samples"]
        ):
            raise ValueError(f"ARM proposal differs from desktop: {key}")
    kinds = {(r["rate_hz"], r["edge"], r["counter"]): r["kind"] for r in specifications}
    statistics = {}
    for kind in sorted(set(kinds.values())):
        statistics[kind] = {}
        for rate in (2500000, 5000000):
            statistics[kind][str(rate)] = {}
            for bins in BINS:
                subset = [
                    r
                    for key, r in indexed[1].items()
                    if key[0] == rate and key[3] == bins and kinds[key[:3]] == kind
                ]
                if subset:
                    statistics[kind][str(rate)][str(bins)] = {
                        "executions": len(subset),
                        **{
                            name: {
                                "mean": float(np.mean([r[name] for r in subset])),
                                **dict(
                                    zip(
                                        ("p50", "p99", "max"),
                                        np.percentile(
                                            [r[name] for r in subset], [50, 99, 100]
                                        ).tolist(),
                                        strict=True,
                                    )
                                ),
                            }
                            for name in TIMINGS
                        },
                    }
    return {
        "verified_results": len(expected),
        "maximum_score_difference": largest_difference,
        "statistics": statistics,
    }
