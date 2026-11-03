"""Fit frozen empirical count and circular-frequency background models."""

from __future__ import annotations

import math
from collections import Counter, defaultdict

MODES = {"poisson", "joint", "joint_frequency", "rate_joint", "rate_joint_frequency"}
COUNT_ALPHA = 32.0
RATE_ALPHA = 128.0
FREQUENCY_BINS = 16


def _validated(rows):
    result = []
    for row in rows:
        counts = row.get("counts")
        frequencies = row.get("frequencies")
        rate = row.get("rate_hz")
        if (
            not isinstance(counts, (list, tuple))
            or len(counts) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in counts
            )
        ):
            raise ValueError("counts must contain two nonnegative integers")
        if not isinstance(frequencies, (list, tuple)) or len(frequencies) != 2:
            raise ValueError("frequencies must contain two receiver lists")
        phases = []
        for count, receiver in zip(counts, frequencies, strict=True):
            if len(receiver) != count:
                raise ValueError("frequency lengths must match counts")
            values = [float(value) for value in receiver]
            if any(not math.isfinite(value) or not 0.0 <= value < 1.0 for value in values):
                raise ValueError("fitted phases must be finite values in [0, 1)")
            phases.append(values)
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            raise ValueError("rate_hz must be a positive integer")
        result.append({"counts": list(counts), "frequencies": phases, "rate_hz": rate})
    if not result:
        raise ValueError("at least one row is required")
    return result


def _histogram(rows):
    counts = Counter((row["counts"][0], row["counts"][1]) for row in rows)
    return [[left, right, counts[(left, right)]] for left, right in sorted(counts)]


def _means(rows):
    size = len(rows)
    return [
        (sum(row["counts"][receiver] for row in rows) + 1.0) / (size + 1.0) for receiver in range(2)
    ]


def _frequency_fit(rows):
    result = []
    for receiver in range(2):
        bins = [0] * FREQUENCY_BINS
        for row in rows:
            for phase in row["frequencies"][receiver]:
                bins[min(int(phase * FREQUENCY_BINS), FREQUENCY_BINS - 1)] += 1
        total = sum(bins)
        result.append([(count + 1.0) / (total + FREQUENCY_BINS) for count in bins])
    return result


def fit(rows, mode):
    """Fit a deterministic JSON-compatible background model."""
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")
    prepared = _validated(rows)
    model = {
        "schema": "rx-empirical-background/v1",
        "mode": mode,
        "rows": len(prepared),
        "pooled_means": _means(prepared),
    }
    if mode != "poisson":
        model["pooled_counts"] = {
            "rows": len(prepared),
            "histogram": _histogram(prepared),
            "tail_weight": COUNT_ALPHA,
        }
    if mode in {"joint_frequency", "rate_joint_frequency"}:
        model["pooled_frequency_probabilities"] = _frequency_fit(prepared)
    if mode.startswith("rate_"):
        by_rate = defaultdict(list)
        for row in prepared:
            by_rate[row["rate_hz"]].append(row)
        rates = {}
        for rate in sorted(by_rate):
            selected = by_rate[rate]
            entry = {
                "rows": len(selected),
                "histogram": _histogram(selected),
                "pooled_pseudorows": RATE_ALPHA,
            }
            if mode == "rate_joint_frequency":
                local_bins = []
                pooled = model["pooled_frequency_probabilities"]
                for receiver in range(2):
                    bins = [0] * FREQUENCY_BINS
                    for row in selected:
                        for phase in row["frequencies"][receiver]:
                            bins[min(int(phase * FREQUENCY_BINS), FREQUENCY_BINS - 1)] += 1
                    total = sum(bins)
                    local_bins.append(
                        [
                            (count + RATE_ALPHA * pooled[receiver][index]) / (total + RATE_ALPHA)
                            for index, count in enumerate(bins)
                        ]
                    )
                entry["frequency_probabilities"] = local_bins
            rates[str(rate)] = entry
        model["rates"] = rates
    return model


def _logaddexp(left, right):
    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    maximum = max(left, right)
    return maximum + math.log1p(math.exp(min(left, right) - maximum))


def _hist_value(spec, left, right):
    for first, second, value in spec["histogram"]:
        if first == left and second == right:
            return value
    return 0


def _pooled_joint_log_probability(model, left, right):
    spec = model["pooled_counts"]
    log_tail = sum(
        count * math.log(mean) - (count + 1) * math.log1p(mean)
        for count, mean in zip((left, right), model["pooled_means"], strict=True)
    )
    observed = _hist_value(spec, left, right)
    log_observed = -math.inf if observed == 0 else math.log(observed)
    return _logaddexp(log_observed, math.log(spec["tail_weight"]) + log_tail) - math.log(
        spec["rows"] + spec["tail_weight"]
    )


def _count_log_probability(model, left, right, rate):
    if model["mode"] == "poisson":
        return sum(
            -mean + count * math.log(mean) - math.lgamma(count + 1)
            for count, mean in zip((left, right), model["pooled_means"], strict=True)
        )
    pooled = _pooled_joint_log_probability(model, left, right)
    if not model["mode"].startswith("rate_"):
        return pooled
    local = model["rates"].get(str(rate))
    if local is None:
        return pooled
    observed = _hist_value(local, left, right)
    log_observed = -math.inf if observed == 0 else math.log(observed)
    return _logaddexp(log_observed, math.log(RATE_ALPHA) + pooled) - math.log(
        local["rows"] + RATE_ALPHA
    )


def log_density(model, row):
    """Return the normalized-phase unordered-set log density for one row."""
    if model.get("schema") != "rx-empirical-background/v1" or model.get("mode") not in MODES:
        raise ValueError("unsupported background model")
    counts = row.get("counts")
    frequencies = row.get("frequencies")
    rate = row.get("rate_hz")
    if (
        not isinstance(counts, (list, tuple))
        or len(counts) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        )
    ):
        raise ValueError("counts must contain two nonnegative integers")
    if not isinstance(frequencies, (list, tuple)) or len(frequencies) != 2:
        raise ValueError("frequencies must contain two receiver lists")
    if any(len(values) != count for count, values in zip(counts, frequencies, strict=True)):
        raise ValueError("frequency lengths must match counts")
    result = (
        _count_log_probability(model, counts[0], counts[1], rate)
        + math.lgamma(counts[0] + 1)
        + math.lgamma(counts[1] + 1)
    )
    if model["mode"] in {"joint_frequency", "rate_joint_frequency"}:
        probabilities = model["pooled_frequency_probabilities"]
        if model["mode"] == "rate_joint_frequency":
            local = model["rates"].get(str(rate))
            if local is not None:
                probabilities = local["frequency_probabilities"]
        for receiver, values in enumerate(frequencies):
            for value in values:
                phase = float(value)
                if not math.isfinite(phase):
                    raise ValueError("phases must be finite")
                phase %= 1.0
                index = min(int(phase * FREQUENCY_BINS), FREQUENCY_BINS - 1)
                result += math.log(FREQUENCY_BINS * probabilities[receiver][index])
    return result
