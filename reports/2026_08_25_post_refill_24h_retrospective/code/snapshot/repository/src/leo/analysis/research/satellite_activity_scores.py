"""Calibrated score costs for raw persistent-satellite activity evidence.

The activity solvers consume negative-log costs rather than detector scores.
This module supplies the smallest auditable bridge for the current prototype:
one predeclared score threshold, a Bernoulli feature model estimated separately
from null and source-bearing calibration inventories, and an explicit per-probe
detection probability.

It is intentionally modest.  A binary score feature discards information in
the full score distribution, but it has two useful properties for the first
raw-inventory replay: weak candidates can be shown to be dominated by a miss,
and calibration can be frozen on different captures before a held-out dwell is
searched.  The resulting costs are not spacecraft-identification odds.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from numbers import Integral
from statistics import NormalDist


def _finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _positive_count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


def _bounded_count(value: object, total: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be an integer in [0, total]")
    result = int(value)
    if not 0 <= result <= total:
        raise ValueError(f"{label} must be an integer in [0, total]")
    return result


def _nonnegative_count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return int(value)


@dataclass(frozen=True, slots=True)
class PilotScoreEvidence:
    """One retained detector candidate before resolution-cell grouping."""

    evidence_id: str
    probe_id: str
    rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    score: float
    acquired_cfo_hz: float | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.probe_id:
            raise ValueError("pilot-score evidence identities are required")
        _nonnegative_count(self.rank, "candidate rank")
        _nonnegative_count(self.local_epoch_sample, "local epoch sample")
        _finite(self.tracking_cfo_hz, "tracking CFO")
        _finite(self.score, "pilot score")
        if self.acquired_cfo_hz is not None:
            _finite(self.acquired_cfo_hz, "acquired CFO")


@dataclass(frozen=True, slots=True)
class PilotScoreGroup:
    """Candidates inside one unresolved epoch/CFO measurement cell."""

    probe_id: str
    member_evidence_ids: tuple[str, ...]
    minimum_rank: int
    maximum_score: float


def group_pilot_score_evidence(
    evidence: tuple[PilotScoreEvidence, ...],
    *,
    epoch_tolerance_samples: int,
    tracking_cfo_tolerance_hz: float,
    acquired_cfo_tolerance_hz: float = 0.0,
) -> tuple[PilotScoreGroup, ...]:
    """Group candidates that cannot support independent transmitter claims.

    Membership is intentionally measurement-level, not a physical source ID.
    A connected component in one probe is formed when candidates differ by no
    more than the declared epoch and tracking-CFO resolution.  Transitive
    closure is conservative for satellite counting: an unresolved chain cannot
    provide independent evidence for multiple transmitters.
    """

    if (
        isinstance(epoch_tolerance_samples, bool)
        or not isinstance(epoch_tolerance_samples, int)
        or epoch_tolerance_samples < 0
    ):
        raise ValueError("epoch tolerance must be a nonnegative integer")
    _nonnegative_count(epoch_tolerance_samples, "epoch tolerance")
    _finite(tracking_cfo_tolerance_hz, "tracking-CFO tolerance")
    if tracking_cfo_tolerance_hz < 0.0:
        raise ValueError("tracking-CFO tolerance must be nonnegative")
    _finite(acquired_cfo_tolerance_hz, "acquired-CFO tolerance")
    if acquired_cfo_tolerance_hz < 0.0:
        raise ValueError("acquired-CFO tolerance must be nonnegative")
    if len({item.evidence_id for item in evidence}) != len(evidence):
        raise ValueError("pilot-score evidence identities must be unique")

    grouped_by_probe: dict[str, list[PilotScoreEvidence]] = defaultdict(list)
    for item in evidence:
        grouped_by_probe[item.probe_id].append(item)
    result: list[PilotScoreGroup] = []
    for probe_id in sorted(grouped_by_probe):
        members = sorted(
            grouped_by_probe[probe_id],
            key=lambda item: (item.rank, item.evidence_id),
        )
        adjacency: list[set[int]] = [set() for _ in members]
        for left in range(len(members)):
            for right in range(left + 1, len(members)):
                epoch_distance = abs(
                    members[left].local_epoch_sample - members[right].local_epoch_sample
                )
                same_resolution_cell = (
                    epoch_distance <= epoch_tolerance_samples
                    and abs(members[left].tracking_cfo_hz - members[right].tracking_cfo_hz)
                    <= tracking_cfo_tolerance_hz
                )
                left_acquired = members[left].acquired_cfo_hz
                right_acquired = members[right].acquired_cfo_hz
                same_acquired_basin = (
                    epoch_distance == 0
                    and left_acquired is not None
                    and right_acquired is not None
                    and abs(left_acquired - right_acquired) <= acquired_cfo_tolerance_hz
                )
                if same_resolution_cell or same_acquired_basin:
                    adjacency[left].add(right)
                    adjacency[right].add(left)
        unseen = set(range(len(members)))
        components: list[list[PilotScoreEvidence]] = []
        while unseen:
            pending = [min(unseen)]
            unseen.remove(pending[0])
            component: list[PilotScoreEvidence] = []
            while pending:
                index = pending.pop()
                component.append(members[index])
                neighbors = sorted(adjacency[index] & unseen, reverse=True)
                unseen.difference_update(neighbors)
                pending.extend(neighbors)
            components.append(component)
        for component in components:
            result.append(
                PilotScoreGroup(
                    probe_id=probe_id,
                    member_evidence_ids=tuple(sorted(item.evidence_id for item in component)),
                    minimum_rank=min(item.rank for item in component),
                    maximum_score=max(item.score for item in component),
                )
            )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.probe_id,
                item.minimum_rank,
                item.member_evidence_ids,
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class NullRankBucketCalibration:
    """Smoothed null frequency for one minimum-rank bucket of score groups."""

    label: str
    minimum_rank: int
    maximum_rank: int | None
    positive_count: int
    total_count: int

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("rank-bucket label is required")
        minimum = _nonnegative_count(self.minimum_rank, "minimum rank")
        if self.maximum_rank is not None:
            maximum = _nonnegative_count(self.maximum_rank, "maximum rank")
            if maximum < minimum:
                raise ValueError("rank-bucket maximum must not precede its minimum")
        total = _nonnegative_count(self.total_count, "rank-bucket total count")
        _bounded_count(self.positive_count, total, "rank-bucket positive count")

    def contains(self, rank: int) -> bool:
        _nonnegative_count(rank, "candidate rank")
        return rank >= self.minimum_rank and (
            self.maximum_rank is None or rank <= self.maximum_rank
        )


def poisson_count_upper_mean(positive_count: int, tail_probability: float) -> float:
    """One-sided upper Poisson mean from an exact lower-tail inversion."""

    count = _nonnegative_count(positive_count, "Poisson positive count")
    _finite(tail_probability, "Poisson tail probability")
    if not 0.0 < tail_probability < 1.0:
        raise ValueError("Poisson tail probability must lie in (0, 1)")
    if count == 0:
        return -math.log(tail_probability)

    def cdf(mean: float) -> float:
        term = math.exp(-mean)
        total = term
        for index in range(1, count + 1):
            term *= mean / index
            total += term
        return total

    lower = 0.0
    upper = float(max(1, count + 1))
    while cdf(upper) > tail_probability:
        upper *= 2.0
    for _ in range(200):
        midpoint = 0.5 * (lower + upper)
        if cdf(midpoint) > tail_probability:
            lower = midpoint
        else:
            upper = midpoint
    return upper


def wilson_probability_lower(
    positive_count: int,
    total_count: int,
    tail_probability: float,
) -> float:
    """One-sided Wilson lower endpoint for a binomial probability."""

    total = _positive_count(total_count, "Wilson total count")
    positive = _bounded_count(positive_count, total, "Wilson positive count")
    _finite(tail_probability, "Wilson tail probability")
    if not 0.0 < tail_probability < 0.5:
        raise ValueError("Wilson tail probability must lie in (0, 0.5)")
    z_score = NormalDist().inv_cdf(1.0 - tail_probability)
    proportion = positive / total
    z_squared = z_score * z_score
    denominator = 1.0 + z_squared / total
    midpoint = proportion + z_squared / (2.0 * total)
    radius = z_score * math.sqrt(
        proportion * (1.0 - proportion) / total + z_squared / (4.0 * total * total)
    )
    return max(0.0, (midpoint - radius) / denominator)


@dataclass(frozen=True, slots=True)
class ConservativeRankMarkCalibration:
    """Least-favorable null intensity and signal mark mass for one rank bucket."""

    label: str
    minimum_rank: int
    maximum_rank: int | None
    null_positive_intensity_upper_per_probe: float
    signal_positive_mark_probability_lower: float

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("rank-mark label is required")
        minimum = _nonnegative_count(self.minimum_rank, "minimum rank")
        if self.maximum_rank is not None:
            maximum = _nonnegative_count(self.maximum_rank, "maximum rank")
            if maximum < minimum:
                raise ValueError("rank-mark maximum must not precede its minimum")
        _finite(
            self.null_positive_intensity_upper_per_probe,
            "null positive intensity upper bound",
        )
        if not 0.0 < self.null_positive_intensity_upper_per_probe <= 1.0:
            raise ValueError("null positive intensity upper bound must lie in (0, 1]")
        _finite(
            self.signal_positive_mark_probability_lower,
            "signal positive mark lower bound",
        )
        if not 0.0 <= self.signal_positive_mark_probability_lower <= 1.0:
            raise ValueError("signal positive mark lower bound must lie in [0, 1]")

    def contains(self, rank: int) -> bool:
        _nonnegative_count(rank, "candidate rank")
        return rank >= self.minimum_rank and (
            self.maximum_rank is None or rank <= self.maximum_rank
        )


@dataclass(frozen=True, slots=True)
class ConservativeRankMarkedPilotScoreCalibration:
    """Conservative marked-point-process costs for positive score groups.

    A positive unresolved detector group is one point whose rank bucket is its
    mark.  Clutter uses a simultaneous worst-source upper intensity per probe;
    a detected signal uses a simultaneous lower mark probability.  This makes
    zero counts conservative and includes the searched opportunity multiplicity
    before the activity and catalogue-search penalties are applied.
    """

    score_threshold: float
    rank_marks: tuple[ConservativeRankMarkCalibration, ...]
    detection_probability: float

    def __post_init__(self) -> None:
        _finite(self.score_threshold, "score threshold")
        if not self.rank_marks:
            raise ValueError("at least one conservative rank mark is required")
        expected_minimum = 0
        labels: set[str] = set()
        for index, mark in enumerate(self.rank_marks):
            if mark.label in labels:
                raise ValueError("conservative rank-mark labels must be unique")
            labels.add(mark.label)
            if mark.minimum_rank != expected_minimum:
                raise ValueError("conservative rank marks must be contiguous from rank zero")
            if index + 1 == len(self.rank_marks):
                if mark.maximum_rank is not None:
                    raise ValueError("the final conservative rank mark must be open-ended")
            elif mark.maximum_rank is None:
                raise ValueError("only the final conservative rank mark may be open-ended")
            if mark.maximum_rank is not None:
                expected_minimum = mark.maximum_rank + 1
        if (
            math.fsum(mark.signal_positive_mark_probability_lower for mark in self.rank_marks)
            > 1.0 + 1e-12
        ):
            raise ValueError("conservative signal rank-mark masses must not exceed one")
        _finite(self.detection_probability, "detection probability")
        if not 0.0 < self.detection_probability < 1.0:
            raise ValueError("detection probability must lie in (0, 1)")

    def mark_for_rank(self, rank: int) -> ConservativeRankMarkCalibration:
        matches = [mark for mark in self.rank_marks if mark.contains(rank)]
        if len(matches) != 1:
            raise ValueError("candidate rank is not covered by exactly one rank mark")
        return matches[0]

    @property
    def missed_detection_cost(self) -> float:
        return -math.log1p(-self.detection_probability)

    def is_positive(self, score: float) -> bool:
        _finite(score, "pilot score")
        return score >= self.score_threshold

    def match_supported(self, rank: int = 0) -> bool:
        return self.mark_for_rank(rank).signal_positive_mark_probability_lower > 0.0

    def clutter_cost(self, score: float, rank: int = 0) -> float:
        if not self.is_positive(score):
            return 0.0
        return -math.log(self.mark_for_rank(rank).null_positive_intensity_upper_per_probe)

    def matched_base_cost(self, score: float, rank: int = 0) -> float:
        if not self.is_positive(score):
            return self.missed_detection_cost
        signal_mass = self.mark_for_rank(rank).signal_positive_mark_probability_lower
        if signal_mass == 0.0:
            return math.inf
        return -math.log(self.detection_probability * signal_mass)

    def match_delta_before_residual(self, score: float, rank: int = 0) -> float:
        return self.matched_base_cost(score, rank) - self.clutter_cost(score, rank)

    def weak_match_is_dominated_by_miss(self) -> bool:
        weak_score = math.nextafter(self.score_threshold, -math.inf)
        return all(
            self.match_delta_before_residual(weak_score, mark.minimum_rank)
            >= self.missed_detection_cost
            for mark in self.rank_marks
        )


@dataclass(frozen=True, slots=True)
class RankAwarePilotScoreCalibration:
    """Resolution-group, minimum-rank-aware null score calibration.

    Signal score frequency remains pooled because the source-conditioned
    calibration inventory is too sparse to estimate a reliable rank-specific
    signal distribution.  Null frequencies match the unit consumed by the
    solver: one unresolved measurement group, stratified by its best rank.
    """

    score_threshold: float
    null_rank_buckets: tuple[NullRankBucketCalibration, ...]
    signal_positive_count: int
    signal_total_count: int
    detection_probability: float
    pseudocount: float = 1.0

    def __post_init__(self) -> None:
        _finite(self.score_threshold, "score threshold")
        if not self.null_rank_buckets:
            raise ValueError("at least one null rank bucket is required")
        expected_minimum = 0
        labels: set[str] = set()
        for index, bucket in enumerate(self.null_rank_buckets):
            if bucket.label in labels:
                raise ValueError("null rank-bucket labels must be unique")
            labels.add(bucket.label)
            if bucket.minimum_rank != expected_minimum:
                raise ValueError("null rank buckets must be contiguous from rank zero")
            if index + 1 == len(self.null_rank_buckets):
                if bucket.maximum_rank is not None:
                    raise ValueError("the final null rank bucket must be open-ended")
            elif bucket.maximum_rank is None:
                raise ValueError("only the final null rank bucket may be open-ended")
            if bucket.maximum_rank is not None:
                expected_minimum = bucket.maximum_rank + 1
        signal_total = _positive_count(self.signal_total_count, "signal total count")
        _bounded_count(self.signal_positive_count, signal_total, "signal positive count")
        _finite(self.detection_probability, "detection probability")
        if not 0.0 < self.detection_probability < 1.0:
            raise ValueError("detection probability must lie in (0, 1)")
        _finite(self.pseudocount, "score pseudocount")
        if self.pseudocount <= 0.0:
            raise ValueError("score pseudocount must be positive")

    @staticmethod
    def _probability(positive_count: int, total_count: int, pseudocount: float) -> float:
        return (positive_count + pseudocount) / (total_count + 2.0 * pseudocount)

    def bucket_for_rank(self, rank: int) -> NullRankBucketCalibration:
        matches = [bucket for bucket in self.null_rank_buckets if bucket.contains(rank)]
        if len(matches) != 1:
            raise ValueError("candidate rank is not covered by exactly one null bucket")
        return matches[0]

    def null_positive_probability(self, rank: int) -> float:
        bucket = self.bucket_for_rank(rank)
        return self._probability(
            bucket.positive_count,
            bucket.total_count,
            self.pseudocount,
        )

    @property
    def signal_positive_probability(self) -> float:
        return self._probability(
            self.signal_positive_count,
            self.signal_total_count,
            self.pseudocount,
        )

    @property
    def missed_detection_cost(self) -> float:
        return -math.log1p(-self.detection_probability)

    def is_positive(self, score: float) -> bool:
        _finite(score, "pilot score")
        return score >= self.score_threshold

    def match_supported(self, rank: int = 0) -> bool:
        self.bucket_for_rank(rank)
        return True

    def clutter_cost(self, score: float, rank: int = 0) -> float:
        positive = self.is_positive(score)
        probability = self.null_positive_probability(rank)
        return -math.log(probability if positive else 1.0 - probability)

    def matched_base_cost(self, score: float, rank: int = 0) -> float:
        del rank
        positive = self.is_positive(score)
        probability = self.signal_positive_probability
        feature_probability = probability if positive else 1.0 - probability
        return -math.log(self.detection_probability) - math.log(feature_probability)

    def match_delta_before_residual(self, score: float, rank: int = 0) -> float:
        return self.matched_base_cost(score, rank) - self.clutter_cost(score, rank)

    def weak_match_is_dominated_by_miss(self) -> bool:
        weak_score = math.nextafter(self.score_threshold, -math.inf)
        return all(
            self.match_delta_before_residual(weak_score, bucket.minimum_rank)
            >= self.missed_detection_cost
            for bucket in self.null_rank_buckets
        )


@dataclass(frozen=True, slots=True)
class BinaryPilotScoreCalibration:
    """Smoothed binary detector-score likelihoods and activity costs.

    ``positive`` means ``score >= score_threshold``.  The two class-conditional
    probabilities use a symmetric Beta pseudocount.  A matched observation pays
    both the detection cost and its signal-class feature cost; an unexplained
    candidate pays its clutter-class feature cost.  An active but unmatched
    probe pays the complementary detection cost.
    """

    score_threshold: float
    null_positive_count: int
    null_total_count: int
    signal_positive_count: int
    signal_total_count: int
    detection_probability: float
    pseudocount: float = 1.0

    def __post_init__(self) -> None:
        _finite(self.score_threshold, "score threshold")
        null_total = _positive_count(self.null_total_count, "null total count")
        signal_total = _positive_count(self.signal_total_count, "signal total count")
        _bounded_count(self.null_positive_count, null_total, "null positive count")
        _bounded_count(self.signal_positive_count, signal_total, "signal positive count")
        _finite(self.detection_probability, "detection probability")
        if not 0.0 < self.detection_probability < 1.0:
            raise ValueError("detection probability must lie in (0, 1)")
        _finite(self.pseudocount, "score pseudocount")
        if self.pseudocount <= 0.0:
            raise ValueError("score pseudocount must be positive")

    @staticmethod
    def _probability(positive_count: int, total_count: int, pseudocount: float) -> float:
        return (positive_count + pseudocount) / (total_count + 2.0 * pseudocount)

    @property
    def null_positive_probability(self) -> float:
        return self._probability(
            self.null_positive_count,
            self.null_total_count,
            self.pseudocount,
        )

    @property
    def signal_positive_probability(self) -> float:
        return self._probability(
            self.signal_positive_count,
            self.signal_total_count,
            self.pseudocount,
        )

    @property
    def missed_detection_cost(self) -> float:
        return -math.log1p(-self.detection_probability)

    def is_positive(self, score: float) -> bool:
        _finite(score, "pilot score")
        return score >= self.score_threshold

    def match_supported(self, rank: int = 0) -> bool:
        del rank
        return True

    def clutter_cost(self, score: float, rank: int = 0) -> float:
        del rank
        positive = self.is_positive(score)
        probability = self.null_positive_probability
        return -math.log(probability if positive else 1.0 - probability)

    def matched_base_cost(self, score: float, rank: int = 0) -> float:
        del rank
        positive = self.is_positive(score)
        probability = self.signal_positive_probability
        feature_probability = probability if positive else 1.0 - probability
        return -math.log(self.detection_probability) - math.log(feature_probability)

    def match_delta_before_residual(self, score: float, rank: int = 0) -> float:
        """Cost change from consuming one clutter candidate as a match."""

        return self.matched_base_cost(score, rank) - self.clutter_cost(score, rank)

    def weak_match_is_dominated_by_miss(self) -> bool:
        """Whether a below-threshold zero-residual match always loses to a miss."""

        weak_score = math.nextafter(self.score_threshold, -math.inf)
        return self.match_delta_before_residual(weak_score) >= self.missed_detection_cost
