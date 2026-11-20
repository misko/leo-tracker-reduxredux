"""Match teacher winners and fit the training-only linear score."""

from collections import Counter
from dataclasses import dataclass
from math import inf, nextafter

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from ..variants.pilot_distill import Rule, coordinates, describe, families, neighbors, stock_winner


@dataclass(frozen=True)
class Label:
    category: str
    positive: int | None = None


def label(teacher, candidates, fast_peaks, frame, tolerance):
    best = stock_winner(teacher)
    if best is None:
        return Label("teacher_negative")
    left = families(teacher, frame, tolerance)
    left_coords, right_coords = (
        tuple(map(coordinates, teacher)),
        tuple(map(coordinates, candidates)),
    )
    winner_group = next(group for group in left if best in group)

    def peer(group, peak):
        return any(
            neighbors(left_coords[i], right_coords[j], frame, tolerance)
            for i in group
            for j in peak.members
        )

    eligible = [i for i, peak in enumerate(fast_peaks) if peer(winner_group, peak)]
    if not eligible:
        return Label("no_roster_match")
    if len(eligible) > 1:
        return Label("ambiguous")
    index = eligible[0]
    peak = fast_peaks[index]
    if sum(peer(group, peak) for group in left) != 1:
        return Label("ambiguous")
    if not any(
        neighbors(left_coords[best], right_coords[j], frame, tolerance) for j in peak.members
    ):
        return Label("no_winner_member_match")
    return Label("shareable", index)


def probe_pairs(teacher, fast):
    for name in ("clock_anchor", "delivery_clocks", "last_sample_counter"):
        if teacher[name] != fast[name]:
            raise ValueError(f"paired streams disagree on {name}")
    for name in (
        "session_id",
        "sample_rate_hz",
        "input_manifest_sha256",
        "raw_recording_authority_digest",
    ):
        if teacher["source"][name] != fast["source"][name]:
            raise ValueError(f"paired streams disagree on {name}")
    if teacher["provenance"]["excluded_windows"] != fast["provenance"]["excluded_windows"]:
        raise ValueError("paired streams disagree on excluded windows")
    rate = fast["source"]["sample_rate_hz"]
    frame, tolerance = round(rate / 750), rate * 0.2e-6
    for a, b in zip(teacher["source"]["probes"], fast["source"]["probes"], strict=True):
        meta_a, meta_b = ({k: v for k, v in probe.items() if k != "candidates"} for probe in (a, b))
        if meta_a != meta_b:
            raise ValueError("paired streams disagree on the physical probe visit")
        left, right = a["candidates"], b["candidates"]
        peaks = describe(right, frame, tolerance)
        yield right, peaks, label(left, right, peaks, frame, tolerance)


def training_rows(pairs):
    eligible, maxima, counts = [], [], Counter()
    for _, peaks, target in pairs:
        counts[target.category] += 1
        if not peaks:
            maxima.append(())
            continue
        maxima.append(peaks)
        if target.category in ("teacher_negative", "shareable"):
            eligible.append((peaks, target))
    if not eligible or counts["shareable"] == 0:
        raise ValueError("training recording has no shareable supervision")
    return eligible, maxima, counts


def prevalence_cutoff(recording_scores, target):
    weights = Counter()
    for scores in recording_scores:
        for score, count in Counter(scores).items():
            if score != -inf:
                weights[score] += count / (len(recording_scores) * len(scores))
    if not weights:
        raise ValueError("threshold requires at least one training score")
    values = sorted(weights, reverse=True)
    options = [(target, nextafter(values[0], inf))]
    admitted = 0.0
    for i, score in enumerate(values):
        admitted += weights[score]
        lower = values[i + 1] if i + 1 < len(values) else nextafter(score, -inf)
        options.append((abs(admitted - target), lower + (score - lower) / 2))
    return min(options, key=lambda p: (round(p[0], 14), p[1]))[1]


def fit(recordings):
    features, labels, weights, target_prevalence = [], [], [], []
    for eligible, maxima, counts in recordings:
        target_prevalence.append(counts["shareable"] / len(maxima))
        for peers, target in eligible:
            for i, peak in enumerate(peers):
                features.append(peak.features)
                labels.append(i == target.positive)
                weights.append(1 / (len(recordings) * len(eligible) * len(peers)))
    samples, labels, weights = np.asarray(features), np.asarray(labels), np.asarray(weights)
    center = weights @ samples
    scale = np.maximum(np.sqrt(weights @ np.square(samples - center)), 1e-9)
    design = (samples - center) / scale

    def objective(parameters):
        intercept, slopes = parameters[0], parameters[1:]
        logit = intercept + design @ slopes
        residual = weights * (expit(logit) - labels)
        loss = weights @ (np.logaddexp(0.0, logit) - labels * logit) + 0.005 * (slopes @ slopes)
        return loss, np.r_[residual.sum(), residual @ design + 0.01 * slopes]

    solution = minimize(
        objective,
        np.zeros(1 + design.shape[1]),
        jac=True,
        bounds=[(None, None), *[(0, None)] * design.shape[1]],
        method="L-BFGS-B",
        options={"ftol": 1e-12, "gtol": 1e-9},
    )
    if not solution.success:
        raise ValueError(f"constrained training failed: {solution.message}")
    rule = Rule(tuple(center), tuple(scale), tuple(solution.x[1:]), solution.x[0], 0.0)
    scores = [
        [max((rule.score(peak) for peak in peers), default=-inf) for peers in maxima]
        for _, maxima, _ in recordings
    ]
    target = sum(target_prevalence) / len(target_prevalence)
    threshold = prevalence_cutoff(scores, target)
    return Rule(rule.center, rule.scale, rule.coefficients, rule.intercept, threshold), dict(
        objective=float(solution.fun),
        training_target_prevalence=target,
        training_predicted_prevalences=[
            sum(score >= threshold for score in group) / len(group) for group in scores
        ],
        training_families=len(labels),
    )


def agreements(pairs, selections):
    counts = Counter()
    totals = {method: Counter() for method in selections}
    oracle = {}
    for i, (candidates, peaks, target) in enumerate(pairs):
        counts[target.category] += 1
        counts["probes"] += 1
        counts["fast_candidates"] += len(candidates)
        counts["fast_families"] += len(peaks)
        counts["duplicate_fast_members"] += len(candidates) - len(peaks)
        counts["stock_admitted_candidates"] += sum(
            row["passed_fractional_margin_gate"] for row in candidates
        )
        members = () if target.positive is None else peaks[target.positive].members
        if target.positive is not None:
            oracle[i] = peaks[target.positive].representative
        for method, selected in selections.items():
            chosen = selected.get(i)
            c = totals[method]
            if chosen is not None:
                c["admitted"] += 1
                c["admitted/" + target.category] += 1
            c["correct_family"] += chosen in members
    return oracle, dict(counts), {k: dict(v) for k, v in totals.items()}
