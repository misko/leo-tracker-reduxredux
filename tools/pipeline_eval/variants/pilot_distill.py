"""Score native peak families with a frozen linear admission rule."""

from dataclasses import dataclass
from math import isfinite, log1p

CFO = "fractional_tracking_cfo_hz"
CONTROL = "fractional_control_score"
GATE = "passed_fractional_margin_gate"
MARGIN = "fractional_margin"
RANK = "candidate_rank"
ALIAS_HZ = 1 / 4.4e-6
FEATURES = ("margin", "margin_gap", "negative_control", "negative_log_rank")


def coordinates(row):
    return row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"], row[CFO]


def wrapped(delta, period):
    return delta - round(delta / period) * period


def neighbors(left, right, frame, tolerance):
    return (
        abs(wrapped(left[0] - right[0], frame)) <= tolerance
        and abs(wrapped(left[1] - right[1], ALIAS_HZ)) <= 1_000
    )


def families(candidates, frame, tolerance):
    """Group by complete-link distance with a deterministic physical order."""
    points = [(epoch % frame, cfo) for epoch, cfo in map(coordinates, candidates)]
    if any(not isfinite(v) for point in points for v in point):
        raise ValueError("native candidate has nonfinite coordinates")
    grouped = []
    for index, point in sorted(enumerate(points), key=lambda pair: pair[1]):
        for group in grouped:
            if all(neighbors(point, points[member], frame, tolerance) for member in group):
                group.append(index)
                break
        else:
            grouped.append([index])
    return tuple(tuple(group) for group in grouped)


def strength(row):
    return row[MARGIN], -row[RANK]


def stock_winner(candidates):
    return max(
        (i for i, row in enumerate(candidates) if row[GATE]),
        key=lambda i: strength(candidates[i]),
        default=None,
    )


@dataclass(frozen=True)
class Peak:
    members: tuple[int, ...]
    representative: int
    features: tuple[float, ...]


def describe(candidates, frame, tolerance):
    groups = families(candidates, frame, tolerance)
    representatives = [max(group, key=lambda i: strength(candidates[i])) for group in groups]
    margins = [candidates[i][MARGIN] for i in representatives]
    peaks = []
    for j, (group, index) in enumerate(zip(groups, representatives, strict=True)):
        row, margin = candidates[index], margins[j]
        rival = max(margins[:j] + margins[j + 1 :], default=0)
        peaks.append(Peak(group, index, (margin, margin - rival, -row[CONTROL], -log1p(row[RANK]))))
    return tuple(peaks)


@dataclass(frozen=True)
class Rule:
    center: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    threshold: float

    def __post_init__(self):
        if (
            not len(self.center) == len(self.scale) == len(self.coefficients) == len(FEATURES)
            or not all(
                map(isfinite, (*self.center, *self.scale, *self.coefficients, self.intercept))
            )
            or any(v <= 0 for v in self.scale)
            or any(v < 0 for v in self.coefficients)
            or not isfinite(self.threshold)
        ):
            raise ValueError("invalid frozen monotone linear score")

    def score(self, peak):
        return self.intercept + sum(
            coefficient * ((value - center) / scale)
            for value, center, scale, coefficient in zip(
                peak.features, self.center, self.scale, self.coefficients, strict=True
            )
        )

    def select(self, candidates, frame, tolerance):
        peaks = describe(candidates, frame, tolerance)
        if not peaks:
            return None
        peak = max(peaks, key=lambda p: (self.score(p), strength(candidates[p.representative])))
        return peak.representative if self.score(peak) >= self.threshold else None


def strongest(probes, count):
    """Take the strongest single fast candidate per probe at the matched winner count."""
    winners = {
        i: max(range(len(rows)), key=lambda j: strength(rows[j]))
        for i, rows in enumerate(probes)
        if rows
    }
    if not 0 <= count <= len(winners):
        raise ValueError("requested probe count is outside the available fast roster")
    order = sorted(winners, key=lambda i: (strength(probes[i][winners[i]]), -i), reverse=True)
    return {i: winners[i] for i in order[:count]}


def apply_winners(document, selected):
    """Rebind a private native stream without changing the fast measurements."""
    probes = document["source"]["probes"]
    if any(
        not (0 <= i < len(probes) and 0 <= j < len(probes[i]["candidates"]))
        for i, j in selected.items()
    ):
        raise ValueError("selected candidate is outside the fast roster")
    adjusted = [
        dict(
            probe,
            candidates=[
                dict(row, **{GATE: selected.get(i) == j})
                for j, row in enumerate(probe["candidates"])
            ],
        )
        for i, probe in enumerate(probes)
    ]
    return dict(document, source=dict(document["source"], probes=adjusted))
