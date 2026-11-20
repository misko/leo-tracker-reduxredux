"""Rank exported GLRT peaks by pilot excess over a causal rolled-pilot floor."""

from bisect import bisect_left, insort
from collections import defaultdict, deque
from math import ceil, isclose, isfinite

HISTORY, MIN_VISITS, QUANTILE = 128, 32, 0.95
ORIGINAL_GATE = 0.025


def lane_key(probe):
    return tuple(probe[key] for key in ("receiver_id", "channel", "actual_rf_hz", "edge"))


def native_rank(peak):
    return peak["fractional_margin"], -peak["candidate_rank"]


class PreviousMaxima:
    """Equal weight per complete visit, with no current or future control in Q95."""

    def __init__(self):
        self.recent = deque()
        self.sorted = []
        self.current_visit = None
        self.current_max = None

    def before(self, visit):
        if self.current_visit is not None and visit < self.current_visit:
            raise ValueError("visits must increase within each RF lane")
        if visit != self.current_visit:
            if self.current_max is not None:
                if len(self.recent) == HISTORY:
                    self.sorted.pop(bisect_left(self.sorted, self.recent.popleft()))
                self.recent.append(self.current_max)
                insort(self.sorted, self.current_max)
            self.current_visit, self.current_max = visit, None
        n = len(self.sorted)
        return self.sorted[ceil(QUANTILE * n) - 1] if n >= MIN_VISITS else None

    def observe(self, control):
        self.current_max = max(control, self.current_max or 0.0)


def evidence(exact, control, floor):
    """Monotone in the matched-minus-rolled excess at fixed background."""
    return (exact - control) / (control + floor)


def check_peak(peak):
    exact, control, margin = (
        peak[f"fractional_{field}"]
        for field in (
            "exact_score",
            "control_score",
            "margin",
        )
    )
    if (
        not all(map(isfinite, (exact, control, margin)))
        or min(exact, control) < 0
        or not isclose(exact - control, margin, rel_tol=0, abs_tol=1e-12)
        or peak["passed_fractional_margin_gate"] != (margin >= ORIGINAL_GATE)
    ):
        raise ValueError("unsupported fractional pilot statistic or gate")


def adjusted_document(document, *, proxy_controls=None):
    """Retain original scores and support, with optional audit-only exchanged controls."""
    source = document["source"]
    lanes = defaultdict(PreviousMaxima)
    probes, changes, floors = [], [], []
    counts = dict(
        probes=len(source["probes"]),
        positive_probes=0,
        warm_ambiguous=0,
        original_candidates=0,
        original_passing=0,
        adjusted_passing=0,
        changed_winner=0,
        changed_cfo=0,
        changed_epoch=0,
        held_proxy_maxima=0,
        held_proxy_above_q95=0,
    )
    for i, probe in enumerate(source["probes"]):
        peaks = probe["candidates"]
        for peak in peaks:
            check_peak(peak)
        controls = (
            [peak["fractional_control_score"] for peak in peaks]
            if proxy_controls is None
            else proxy_controls[i]
        )
        lane = lanes[lane_key(probe)]
        floor = lane.before(probe["visit_index"])
        eligible = [j for j, peak in enumerate(peaks) if peak["passed_fractional_margin_gate"]]
        counts["positive_probes"] += bool(eligible)
        counts["original_candidates"] += len(peaks)
        counts["original_passing"] += len(eligible)
        counts["adjusted_passing"] += len(eligible)
        if floor is not None and floor > 0:
            floors.append(floor)
            if controls:
                counts["held_proxy_maxima"] += 1
                counts["held_proxy_above_q95"] += max(controls) > floor
            if len(eligible) > 1:
                counts["warm_ambiguous"] += 1
                strict = max(eligible, key=lambda j: native_rank(peaks[j]))
                adjusted = max(
                    eligible,
                    key=lambda j: (
                        evidence(peaks[j]["fractional_exact_score"], controls[j], floor),
                        *native_rank(peaks[j]),
                    ),
                )
                if adjusted != strict:
                    old, new = peaks[strict], peaks[adjusted]
                    outranks = {j for j in eligible if native_rank(peaks[j]) > native_rank(new)}
                    probe = dict(
                        probe, candidates=[p for j, p in enumerate(peaks) if j not in outranks]
                    )
                    counts["adjusted_passing"] -= len(outranks)
                    counts["changed_winner"] += 1
                    counts["changed_cfo"] += (
                        old["fractional_tracking_cfo_hz"] != new["fractional_tracking_cfo_hz"]
                    )
                    counts["changed_epoch"] += any(
                        old[k] != new[k]
                        for k in (
                            "integer_epoch_sample",
                            "fractional_epoch_offset_samples",
                        )
                    )
                    changes.append(
                        dict(
                            probe_index=i,
                            receiver_id=probe["receiver_id"],
                            visit=probe["visit_index"],
                            old_rank=old["candidate_rank"],
                            new_rank=new["candidate_rank"],
                            old_cfo_hz=old["fractional_tracking_cfo_hz"],
                            new_cfo_hz=new["fractional_tracking_cfo_hz"],
                            old_margin=old["fractional_margin"],
                            new_margin=new["fractional_margin"],
                            previous_maximum_q95=floor,
                        )
                    )
        if controls:
            lane.observe(max(controls))
        probes.append(probe)
    return dict(document, source=dict(source, probes=probes)), counts, floors, changes
