#!/usr/bin/env python3
"""Replay the full raw GLRT64 peak inventory against a small satellite set.

Unlike the branch-conditioned replay, this read-only research adapter starts
from every retained PilotScanV3 acquisition basin.  It keeps the native probe
cadence, groups candidates that the persisted detector does not independently
resolve into one exclusion cell,
proposes a bounded bank of delay/CFO states for each supplied catalogue object,
and invokes the exact grouped semi-Markov oracle.

The result is exact only over the retained 2--3 catalogue objects and the
reported pruned nuisance-state bank.  It is not a full-catalogue search or a
spacecraft-identification product.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.grouped_satellite_activity import (  # type: ignore[import-untyped]
    decode_grouped_nuisance_states,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    decode_single_satellite,
)
from leo.analysis.research.satellite_activity_scores import (  # type: ignore[import-untyped]
    BinaryPilotScoreCalibration,
    ConservativeRankMarkCalibration,
    ConservativeRankMarkedPilotScoreCalibration,
    NullRankBucketCalibration,
    PilotScoreEvidence,
    RankAwarePilotScoreCalibration,
    group_pilot_score_evidence,
    poisson_count_upper_mean,
    wilson_probability_lower,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.propagation import parse_element_sets  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.replay_joint_fixed_satellite_activity import (  # noqa: E402
    INPUT_SCHEMA,
    _doppler_curve,
    _file_digest,
    _ordered_schedule,
    _read_json,
    _refuse_qnap_output,
    _unique_satellite_index,
    _window_inventory,
)
from tools.replay_joint_fixed_satellite_activity import (  # noqa: E402
    ReplayConfig as _WindowConfig,
)

OUTPUT_SCHEMA = "org.leo.research.raw-grouped-satellite-activity-replay/v1"
CALIBRATION_SCHEMA_V1 = "org.leo.research.raw-pilot-activity-score-calibration/v1"
CALIBRATION_SCHEMA_V2 = "org.leo.research.raw-pilot-activity-score-calibration/v2"
CALIBRATION_SCHEMA_V3 = "org.leo.research.raw-pilot-activity-score-calibration/v3"
CALIBRATION_SCHEMA = CALIBRATION_SCHEMA_V3
V3_RANK_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("rank0", 0, 0),
    ("rank1", 1, 1),
    ("rank2_4", 2, 4),
    ("rank5_plus", 5, None),
)
type ScoreCalibration = (
    BinaryPilotScoreCalibration
    | RankAwarePilotScoreCalibration
    | ConservativeRankMarkedPilotScoreCalibration
)


def _finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be nonnegative")


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _sha256_digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be a canonical lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class RawReplayConfig:
    """Bounded nuisance search and activity settings for one raw replay."""

    cell_duration_s: float = 0.1
    minimum_active_duration_s: float = 0.5
    allow_left_censored: bool = False
    allow_right_censored: bool = False
    cfo_sigma_hz: float = 100.0
    satellite_cost: float = 5.25
    episode_cost: float = 5.75
    huber_threshold: float = 1.345
    delay_min_s: float = -2.0
    delay_max_s: float = 2.0
    delay_step_s: float = 0.1
    delay_prior_mean_s: float = 0.0
    delay_prior_sigma_s: float = 0.5
    duplicate_cfo_tolerance_hz: float = 0.0
    resolution_epoch_tolerance_samples: int = 1
    resolution_tracking_cfo_tolerance_hz: float = 500.0
    mode_bin_hz: float = 100.0
    mode_half_width_hz: float = 300.0
    modes_per_delay: int = 2
    retained_states_per_catalog: int = 4
    maximum_state_combinations: int = 256
    horizon_mask_deg: float = 0.0

    def __post_init__(self) -> None:
        for value, label in (
            (self.cell_duration_s, "activity-cell duration"),
            (self.minimum_active_duration_s, "minimum active duration"),
            (self.cfo_sigma_hz, "CFO sigma"),
            (self.huber_threshold, "Huber threshold"),
            (self.delay_step_s, "delay step"),
            (self.delay_prior_sigma_s, "delay-prior sigma"),
            (self.mode_bin_hz, "CFO-mode bin width"),
            (self.mode_half_width_hz, "CFO-mode half-width"),
        ):
            _positive(value, label)
        _nonnegative(self.duplicate_cfo_tolerance_hz, "duplicate-CFO tolerance")
        _nonnegative(
            self.resolution_tracking_cfo_tolerance_hz,
            "tracking-CFO resolution tolerance",
        )
        for value, label in (
            (self.satellite_cost, "satellite cost"),
            (self.episode_cost, "episode cost"),
        ):
            _nonnegative(value, label)
        for value, label in (
            (self.delay_min_s, "minimum delay"),
            (self.delay_max_s, "maximum delay"),
            (self.delay_prior_mean_s, "delay-prior mean"),
            (self.horizon_mask_deg, "horizon mask"),
        ):
            _finite(value, label)
        if self.delay_max_s < self.delay_min_s:
            raise ValueError("maximum delay must not be below minimum delay")
        if not 0.0 <= self.horizon_mask_deg <= 90.0:
            raise ValueError("horizon mask must lie in [0, 90]")
        for value, label in (
            (self.modes_per_delay, "modes per delay"),
            (self.retained_states_per_catalog, "retained states per catalog"),
            (self.maximum_state_combinations, "maximum state combinations"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if (
            isinstance(self.resolution_epoch_tolerance_samples, bool)
            or not isinstance(self.resolution_epoch_tolerance_samples, int)
            or self.resolution_epoch_tolerance_samples < 0
        ):
            raise ValueError("epoch-resolution tolerance must be a nonnegative integer")
        minimum_cells = self.minimum_active_duration_s / self.cell_duration_s
        if not math.isclose(minimum_cells, round(minimum_cells), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("minimum active duration must be a whole number of cells")

    @property
    def minimum_active_cells(self) -> int:
        return round(self.minimum_active_duration_s / self.cell_duration_s)

    @property
    def delay_grid(self) -> tuple[float, ...]:
        count_value = (self.delay_max_s - self.delay_min_s) / self.delay_step_s
        count = round(count_value)
        if not math.isclose(count_value, count, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("delay bounds must contain a whole number of steps")
        if count + 1 > 201:
            raise ValueError("raw replay refuses more than 201 delay-grid points")
        return tuple(self.delay_min_s + index * self.delay_step_s for index in range(count + 1))


@dataclass(frozen=True, slots=True)
class _RawObservation:
    observation_id: str
    exclusion_group_id: str
    probe_id: str
    probe_index: int
    cfo_hz: float
    margin: float
    rank: int
    group_minimum_rank: int
    group_maximum_margin: float
    group_member_count: int
    local_epoch_offset_s: float


@dataclass(frozen=True, slots=True)
class _RawInventory:
    problem: SatelliteActivityProblem
    observations: tuple[_RawObservation, ...]
    source_candidate_count: int
    returned_candidate_count: int
    exclusion_group_count: int
    positive_candidate_count: int
    positive_exclusion_group_count: int
    modeled_exclusion_group_count: int
    unsupported_positive_candidate_count: int
    unsupported_positive_exclusion_group_count: int
    dominated_weak_candidate_count: int
    dominated_weak_exclusion_group_count: int
    elided_clutter_constant: float
    saturated_probe_count: int
    local_epoch_min_s: float | None
    local_epoch_max_s: float | None
    scan_path: Path
    scan_digest: str


@dataclass(frozen=True, slots=True)
class _OffsetMode:
    cfo_offset_hz: float
    support_group_count: int
    support_probe_count: int


@dataclass(frozen=True, slots=True)
class _StateEvaluation:
    hypothesis: SingleSatelliteHypothesis
    proposal: _OffsetMode
    single_total_cost: float
    single_delta_from_null: float
    single_selected: bool
    minimum_elevation_deg: float
    maximum_elevation_deg: float


def _score(document: dict[str, Any]) -> ScoreCalibration:
    schema = document.get("schema")
    if schema not in {
        CALIBRATION_SCHEMA_V1,
        CALIBRATION_SCHEMA_V2,
        CALIBRATION_SCHEMA_V3,
    }:
        raise ValueError("expected raw pilot activity score calibration schema V1, V2, or V3")
    sources = document.get("sources")
    if not isinstance(sources, dict) or sources.get("disjoint_pilot_scan_digests") is not True:
        raise ValueError("score calibration does not prove disjoint pilot-scan sources")
    null_sources = sources.get("null")
    signal_sources = sources.get("signal")
    if not isinstance(null_sources, list) or not null_sources:
        raise ValueError("score calibration has no null pilot-scan sources")
    if not isinstance(signal_sources, list) or not signal_sources:
        raise ValueError("score calibration has no signal pilot-scan sources")

    def source_digest(item: object, *, signal: bool) -> str:
        if not isinstance(item, dict):
            raise ValueError("score calibration source entry is not an object")
        source = item.get("pilot_scan") if signal else item
        if not isinstance(source, dict):
            raise ValueError("score calibration signal source omits its pilot scan")
        return _sha256_digest(
            source.get("file_digest"),
            "score calibration pilot-scan digest",
        )

    null_digests = [source_digest(item, signal=False) for item in null_sources]
    signal_digests = [source_digest(item, signal=True) for item in signal_sources]
    all_digests = null_digests + signal_digests
    if len(set(all_digests)) != len(all_digests):
        raise ValueError("score calibration reuses a pilot-scan source")
    null = document.get("null")
    signal = document.get("signal")
    if not isinstance(null, dict) or not isinstance(signal, dict):
        raise ValueError("score calibration omits null or signal counts")
    score_threshold = float(document["score_threshold"])
    detection_probability = float(document["detection_probability"])
    if schema == CALIBRATION_SCHEMA_V1:
        return BinaryPilotScoreCalibration(
            score_threshold=score_threshold,
            null_positive_count=int(null["positive_count"]),
            null_total_count=int(null["total_count"]),
            signal_positive_count=int(signal["positive_count"]),
            signal_total_count=int(signal["total_count"]),
            detection_probability=detection_probability,
            pseudocount=float(document["pseudocount"]),
        )
    raw_buckets = null.get("rank_buckets")
    if not isinstance(raw_buckets, list) or not raw_buckets:
        raise ValueError("V2 score calibration omits null rank buckets")
    if schema == CALIBRATION_SCHEMA_V3:
        if len(raw_buckets) != len(V3_RANK_BUCKETS):
            raise ValueError("V3 score calibration has the wrong rank-bucket inventory")
        confidence = document.get("confidence")
        if not isinstance(confidence, dict):
            raise ValueError("V3 score calibration omits confidence accounting")
        familywise_alpha = float(confidence["familywise_alpha"])
        if not math.isfinite(familywise_alpha) or not 0.0 < familywise_alpha < 1.0:
            raise ValueError("V3 familywise alpha must lie in (0, 1)")
        bucket_count = len(raw_buckets)
        source_count = len(null_digests)
        if (
            _integer(confidence["rank_bucket_count"], "V3 rank-bucket count", minimum=1)
            != (bucket_count)
            or _integer(confidence["null_source_count"], "V3 null-source count", minimum=1)
            != source_count
        ):
            raise ValueError("V3 confidence search counts disagree with its sources")
        expected_null_tail = familywise_alpha / (2.0 * bucket_count * source_count)
        expected_signal_tail = familywise_alpha / (2.0 * bucket_count)
        if not math.isclose(
            float(confidence["null_source_bucket_tail_probability"]),
            expected_null_tail,
            rel_tol=0.0,
            abs_tol=1e-15,
        ) or not math.isclose(
            float(confidence["signal_bucket_tail_probability"]),
            expected_signal_tail,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError("V3 confidence tail probabilities are inconsistent")
        if (
            confidence.get("null_bound") != "worst-source-exact-poisson-count-upper"
            or confidence.get("signal_bound") != "simultaneous-wilson-mark-probability-lower"
        ):
            raise ValueError("V3 score calibration declares an unsupported bound method")

        signal_group_count = _integer(signal["group_count"], "V3 signal group count", minimum=1)
        signal_positive_group_count = _integer(
            signal["positive_group_count"], "V3 signal positive-group count"
        )
        if signal_positive_group_count > signal_group_count:
            raise ValueError("V3 signal positive-group count exceeds its group count")
        declared_null_sources: dict[str, dict[str, int]] = {}
        for raw_source, digest in zip(null_sources, null_digests, strict=True):
            if not isinstance(raw_source, dict):
                raise ValueError("V3 null source entry is not an object")
            declared_group_count = _integer(
                raw_source.get("resolution_group_count"),
                "V3 null source resolution-group count",
            )
            declared_positive_count = _integer(
                raw_source.get("positive_count"),
                "V3 null source positive-group count",
            )
            if declared_positive_count > declared_group_count:
                raise ValueError("V3 null source positive count exceeds its group count")
            declared_null_sources[digest] = {
                "probe_count": _integer(
                    raw_source.get("detection_count"),
                    "V3 null source probe count",
                    minimum=1,
                ),
                "group_count": declared_group_count,
                "positive_group_count": declared_positive_count,
                "raw_row_count": _integer(
                    raw_source.get("raw_glrt64_row_count"),
                    "V3 null source raw-row count",
                ),
                "deduplicated_row_count": _integer(
                    raw_source.get("deduplicated_glrt64_row_count"),
                    "V3 null source deduplicated-row count",
                ),
            }
            counts = declared_null_sources[digest]
            if not (
                counts["raw_row_count"] >= counts["deduplicated_row_count"] >= counts["group_count"]
            ):
                raise ValueError("V3 null source row/group accounting is impossible")
        declared_signal_sources: list[dict[str, int]] = []
        for raw_source in signal_sources:
            if not isinstance(raw_source, dict):
                raise ValueError("V3 signal source entry is not an object")
            declared_group_count = _integer(
                raw_source.get("resolution_group_count"),
                "V3 signal source resolution-group count",
            )
            unique_probe_count = _integer(
                raw_source.get("unique_resolution_group_probe_count"),
                "V3 signal source unique group-probe count",
            )
            declared_positive_count = _integer(
                raw_source.get("positive_count"),
                "V3 signal source positive-group count",
            )
            if unique_probe_count != declared_group_count:
                raise ValueError("V3 signal source has more than one group per probe")
            if declared_positive_count > declared_group_count:
                raise ValueError("V3 signal source positive count exceeds its group count")
            declared_signal_sources.append(
                {
                    "group_count": declared_group_count,
                    "positive_group_count": declared_positive_count,
                    "unique_probe_count": unique_probe_count,
                    "raw_row_count": _integer(
                        raw_source.get("raw_glrt64_row_count"),
                        "V3 signal source raw-row count",
                    ),
                    "deduplicated_row_count": _integer(
                        raw_source.get("deduplicated_glrt64_row_count"),
                        "V3 signal source deduplicated-row count",
                    ),
                }
            )
            counts = declared_signal_sources[-1]
            if not (
                counts["raw_row_count"] >= counts["deduplicated_row_count"] >= counts["group_count"]
            ):
                raise ValueError("V3 signal source row/group accounting is impossible")
        marks = []
        aggregate_null_group_count = 0
        aggregate_null_positive_count = 0
        aggregate_signal_positive_count = 0
        source_bucket_totals = {
            digest: {"group_count": 0, "positive_group_count": 0} for digest in null_digests
        }
        for raw, expected_bucket in zip(raw_buckets, V3_RANK_BUCKETS, strict=True):
            if not isinstance(raw, dict):
                raise ValueError("V3 rank-mark bucket is not an object")
            expected_label, expected_minimum, expected_maximum = expected_bucket
            observed_label = raw.get("label")
            observed_minimum = _integer(raw.get("minimum_rank"), "V3 rank-mark minimum rank")
            raw_maximum = raw.get("maximum_rank")
            observed_maximum = (
                None if raw_maximum is None else _integer(raw_maximum, "V3 rank-mark maximum rank")
            )
            if (
                observed_label != expected_label
                or observed_minimum != expected_minimum
                or observed_maximum != expected_maximum
            ):
                raise ValueError("V3 rank-mark buckets disagree with the fixed schema")
            null_bucket = raw.get("null")
            signal_bucket = raw.get("signal")
            if not isinstance(null_bucket, dict) or not isinstance(signal_bucket, dict):
                raise ValueError("V3 rank-mark bucket omits null or signal bounds")
            source_bounds = null_bucket.get("source_bounds")
            if not isinstance(source_bounds, list) or len(source_bounds) != source_count:
                raise ValueError("V3 rank-mark bucket has incomplete null source bounds")
            observed_source_digests: set[str] = set()
            recomputed_source_bounds = []
            for source_bound in source_bounds:
                if not isinstance(source_bound, dict):
                    raise ValueError("V3 null source bound is not an object")
                digest = _sha256_digest(
                    source_bound["pilot_scan_digest"],
                    "V3 null source-bound pilot-scan digest",
                )
                if digest not in null_digests or digest in observed_source_digests:
                    raise ValueError("V3 null source bound has an unknown or repeated digest")
                observed_source_digests.add(digest)
                probe_count = _integer(
                    source_bound["probe_count"], "V3 null source-bound probe count", minimum=1
                )
                group_count = _integer(
                    source_bound["group_count"], "V3 null source-bound group count"
                )
                positive_count = _integer(
                    source_bound["positive_group_count"],
                    "V3 null source-bound positive-group count",
                )
                if positive_count > group_count:
                    raise ValueError("V3 null source bound has invalid counts")
                declared_source = declared_null_sources[digest]
                if probe_count != declared_source["probe_count"]:
                    raise ValueError("V3 null source-bound probe count disagrees with source")
                source_bucket_totals[digest]["group_count"] += group_count
                source_bucket_totals[digest]["positive_group_count"] += positive_count
                upper_mean = poisson_count_upper_mean(
                    positive_count,
                    expected_null_tail,
                )
                upper_intensity = upper_mean / probe_count
                if not math.isclose(
                    float(source_bound["poisson_count_upper_mean"]),
                    upper_mean,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ) or not math.isclose(
                    float(source_bound["positive_intensity_upper_per_probe"]),
                    upper_intensity,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                ):
                    raise ValueError("V3 null source bound arithmetic is inconsistent")
                recomputed_source_bounds.append((upper_intensity, digest))
            worst_intensity, worst_digest = max(recomputed_source_bounds)
            if str(
                null_bucket["worst_source_pilot_scan_digest"]
            ) != worst_digest or not math.isclose(
                float(null_bucket["positive_intensity_upper_per_probe"]),
                worst_intensity,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise ValueError("V3 worst-source null envelope is inconsistent")

            bucket_null_group_count = _integer(
                null_bucket["group_count"], "V3 null bucket group count"
            )
            bucket_null_positive_count = _integer(
                null_bucket["positive_group_count"],
                "V3 null bucket positive-group count",
            )
            if bucket_null_positive_count > bucket_null_group_count:
                raise ValueError("V3 null bucket positive count exceeds its group count")
            if bucket_null_group_count != sum(
                _integer(item["group_count"], "V3 null source-bound group count")
                for item in source_bounds
            ) or bucket_null_positive_count != sum(
                _integer(
                    item["positive_group_count"],
                    "V3 null source-bound positive-group count",
                )
                for item in source_bounds
            ):
                raise ValueError("V3 aggregate null rank-bucket counts are inconsistent")
            bucket_signal_count = _integer(
                signal_bucket["positive_group_count"],
                "V3 signal bucket positive-group count",
            )
            if bucket_signal_count > signal_group_count:
                raise ValueError("V3 signal bucket positive count exceeds its denominator")
            if (
                _integer(
                    signal_bucket["total_group_count"],
                    "V3 signal bucket denominator",
                    minimum=1,
                )
                != signal_group_count
            ):
                raise ValueError("V3 signal rank-mark denominator is inconsistent")
            signal_lower = wilson_probability_lower(
                bucket_signal_count,
                signal_group_count,
                expected_signal_tail,
            )
            if not math.isclose(
                float(signal_bucket["positive_mark_probability_lower"]),
                signal_lower,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise ValueError("V3 signal rank-mark bound arithmetic is inconsistent")
            aggregate_null_group_count += bucket_null_group_count
            aggregate_null_positive_count += bucket_null_positive_count
            aggregate_signal_positive_count += bucket_signal_count
            marks.append(
                ConservativeRankMarkCalibration(
                    label=expected_label,
                    minimum_rank=expected_minimum,
                    maximum_rank=expected_maximum,
                    null_positive_intensity_upper_per_probe=worst_intensity,
                    signal_positive_mark_probability_lower=signal_lower,
                )
            )
        if (
            aggregate_null_group_count != _integer(null["group_count"], "V3 null group count")
            or aggregate_null_positive_count
            != _integer(null["positive_group_count"], "V3 null positive-group count")
            or aggregate_signal_positive_count != signal_positive_group_count
        ):
            raise ValueError("V3 top-level rank-mark accounting is inconsistent")
        for digest, totals in source_bucket_totals.items():
            declared_source = declared_null_sources[digest]
            if (
                totals["group_count"] != declared_source["group_count"]
                or totals["positive_group_count"] != declared_source["positive_group_count"]
            ):
                raise ValueError("V3 null source bounds disagree with source accounting")
        if sum(item["group_count"] for item in declared_signal_sources) != (
            signal_group_count
        ) or sum(item["positive_group_count"] for item in declared_signal_sources) != (
            signal_positive_group_count
        ):
            raise ValueError("V3 signal sources disagree with top-level accounting")
        if math.fsum(mark.signal_positive_mark_probability_lower for mark in marks) > 1.0 + 1e-12:
            raise ValueError("V3 conservative signal mark masses exceed one")
        accounting = document.get("accounting")
        if not isinstance(accounting, dict):
            raise ValueError("V3 score calibration omits inventory accounting")
        expected_accounting = {
            "null_input_file_count": source_count,
            "signal_component_spec_count": len(signal_sources),
            "null_raw_glrt64_row_count": sum(
                item["raw_row_count"] for item in declared_null_sources.values()
            ),
            "null_deduplicated_glrt64_row_count": sum(
                item["deduplicated_row_count"] for item in declared_null_sources.values()
            ),
            "null_resolution_group_count": aggregate_null_group_count,
            "signal_raw_glrt64_row_count": sum(
                item["raw_row_count"] for item in declared_signal_sources
            ),
            "signal_deduplicated_glrt64_row_count": sum(
                item["deduplicated_row_count"] for item in declared_signal_sources
            ),
            "signal_resolution_group_count": signal_group_count,
            "signal_unique_resolution_group_probe_count": sum(
                item["unique_probe_count"] for item in declared_signal_sources
            ),
        }
        if any(
            _integer(accounting.get(label), f"V3 accounting field {label}") != expected
            for label, expected in expected_accounting.items()
        ):
            raise ValueError("V3 inventory accounting disagrees with its sources")
        return ConservativeRankMarkedPilotScoreCalibration(
            score_threshold=score_threshold,
            rank_marks=tuple(marks),
            detection_probability=detection_probability,
        )

    buckets = []
    for raw in raw_buckets:
        if not isinstance(raw, dict):
            raise ValueError("V2 null rank bucket is not an object")
        maximum = raw.get("maximum_rank")
        buckets.append(
            NullRankBucketCalibration(
                label=str(raw["label"]),
                minimum_rank=int(raw["minimum_rank"]),
                maximum_rank=None if maximum is None else int(maximum),
                positive_count=int(raw["positive_count"]),
                total_count=int(raw["total_count"]),
            )
        )
    return RankAwarePilotScoreCalibration(
        score_threshold=score_threshold,
        null_rank_buckets=tuple(buckets),
        signal_positive_count=int(signal["positive_count"]),
        signal_total_count=int(signal["total_count"]),
        detection_probability=detection_probability,
        pseudocount=float(document["pseudocount"]),
    )


def _validate_calibration_grouping(
    document: dict[str, Any],
    config: RawReplayConfig,
) -> None:
    if document.get("schema") == CALIBRATION_SCHEMA_V1:
        if (
            config.resolution_epoch_tolerance_samples != 0
            or config.resolution_tracking_cfo_tolerance_hz != 0.0
        ):
            raise ValueError("V1 row calibration cannot score resolution-grouped replay")
        return
    grouping = document.get("grouping")
    if not isinstance(grouping, dict):
        raise ValueError("V2 score calibration omits resolution grouping")
    if int(grouping.get("epoch_tolerance_samples", -1)) != (
        config.resolution_epoch_tolerance_samples
    ) or not math.isclose(
        float(grouping.get("tracking_cfo_tolerance_hz", math.nan)),
        config.resolution_tracking_cfo_tolerance_hz,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("score calibration and replay use different resolution grouping")
    if document.get("schema") == CALIBRATION_SCHEMA_V3 and not math.isclose(
        float(grouping.get("exact_duplicate_acquired_cfo_tolerance_hz", math.nan)),
        config.duplicate_cfo_tolerance_hz,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("score calibration and replay use different exact-basin grouping")


def _glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    scores = [item for item in candidate.get("scores", ()) if item.get("method") == "glrt64"]
    if len(scores) != 1:
        raise ValueError("raw pilot candidate does not contain exactly one GLRT64 score")
    score = scores[0]
    exact = float(score["exact_score"])
    control = float(score["control_score"])
    margin = float(score["margin"])
    if not all(math.isfinite(value) for value in (exact, control, margin)):
        raise ValueError("raw GLRT64 score fields must be finite")
    if not math.isclose(margin, exact - control, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("raw GLRT64 margin disagrees with exact minus control")
    return score


def _exclusion_groups(
    rows: list[dict[str, Any]],
    *,
    probe_id: str,
    acquired_tolerance_hz: float,
    epoch_tolerance_samples: int,
    tracking_tolerance_hz: float,
) -> tuple[tuple[dict[str, Any], str, float, int, int], ...]:
    """Collapse candidates that are unresolved at the persisted measurement scale.

    The persisted alias map does not bind the full raw candidate inventory, so
    non-identical integer CFO aliases cannot yet be assigned one authoritative
    physical exclusion group.  This narrower rule prevents two candidates in
    one local epoch/tracking-CFO resolution cell from being asserted as two
    independently resolved transmitters.  It does not claim that the members
    came from the same physical source.
    """

    row_by_id = {str(row["observation_id"]): row for row in rows}
    groups = group_pilot_score_evidence(
        tuple(
            PilotScoreEvidence(
                evidence_id=observation_id,
                probe_id=probe_id,
                rank=int(row["rank"]),
                local_epoch_sample=int(row["local_epoch_sample"]),
                tracking_cfo_hz=float(row["cfo_hz"]),
                score=float(row["margin"]),
                acquired_cfo_hz=float(row["acquired_cfo_hz"]),
            )
            for observation_id, row in sorted(row_by_id.items())
        ),
        epoch_tolerance_samples=epoch_tolerance_samples,
        tracking_cfo_tolerance_hz=tracking_tolerance_hz,
        acquired_cfo_tolerance_hz=acquired_tolerance_hz,
    )
    result = []
    for group in groups:
        member_ids = list(group.member_evidence_ids)
        group_id = canonical_digest(
            {
                "probe_id": probe_id,
                "member_observation_ids": member_ids,
                "epoch_tolerance_samples": epoch_tolerance_samples,
                "tracking_cfo_tolerance_hz": tracking_tolerance_hz,
                "method": "glrt64",
            }
        )
        for member_id in member_ids:
            result.append(
                (
                    row_by_id[member_id],
                    group_id,
                    group.maximum_score,
                    group.minimum_rank,
                    len(member_ids),
                )
            )
    return tuple(sorted(result, key=lambda item: (str(item[0]["observation_id"]), item[1])))


def _load_raw_inventory(
    *,
    dataset: dict[str, Any],
    window_rows: tuple[dict[str, Any], ...],
    window_start_sample: int,
    window_cell_samples: int,
    window_cell_count: int,
    calibration: ScoreCalibration,
    config: RawReplayConfig,
) -> _RawInventory:
    source_products = dataset.get("source_products")
    if not isinstance(source_products, dict) or not isinstance(source_products.get("scan"), dict):
        raise ValueError("duration input does not identify its raw pilot-scan product")
    scan_evidence = source_products["scan"]
    scan_path = Path(str(scan_evidence["path"]))
    expected_digest = str(scan_evidence["file_digest"])
    observed_digest = _file_digest(scan_path)
    if observed_digest != expected_digest:
        raise ValueError("raw pilot-scan file digest disagrees with duration input")
    scan = _read_json(scan_path)
    if scan.get("schema_version") != 3 or scan.get("algorithm_version") != "standard-pilot-scan-v3":
        raise ValueError("raw replay requires Standard PilotScanV3")
    if scan.get("frequency_coordinate") != "baseband_cfo_hz":
        raise ValueError("raw pilot scan is not in the baseband CFO coordinate")
    if scan.get("frequency_reference") != "uncalibrated_prior":
        raise ValueError("raw pilot scan unexpectedly claims calibrated frequency authority")
    schedule_evidence = source_products.get("schedule")
    alias_evidence = source_products.get("alias_map")
    if not isinstance(schedule_evidence, dict) or not isinstance(alias_evidence, dict):
        raise ValueError("duration input omits raw schedule or alias-map evidence")
    schedule_path = Path(str(schedule_evidence["path"]))
    alias_path = Path(str(alias_evidence["path"]))
    if _file_digest(schedule_path) != str(schedule_evidence["file_digest"]):
        raise ValueError("raw probe-schedule file digest disagrees with duration input")
    if _file_digest(alias_path) != str(alias_evidence["file_digest"]):
        raise ValueError("raw alias-map file digest disagrees with duration input")
    schedule = _read_json(schedule_path)
    alias_map = _read_json(alias_path)
    if schedule.get("schema_version") != 2 or int(schedule["truncated_probe_count"]) != 0:
        raise ValueError("raw replay requires an untruncated ProbeScheduleV2")
    if int(schedule["source_probe_count"]) != int(schedule["returned_probe_count"]):
        raise ValueError("raw probe schedule source/returned accounting is inconsistent")
    if scan.get("probe_schedule_digest") != schedule.get("schedule_digest"):
        raise ValueError("raw pilot scan does not bind its probe schedule")
    if alias_map.get("schema_version") != 2:
        raise ValueError("raw replay requires CFO AliasMapV2 lineage evidence")
    if alias_map.get("pilot_scan_digest") != canonical_digest(scan):
        raise ValueError("raw alias map does not bind the supplied pilot scan")

    schedule_by_sample = {int(item["probe_sample_start"]): item for item in window_rows}
    if len(schedule_by_sample) != len(window_rows):
        raise ValueError("raw replay window schedule has duplicate sample starts")
    probe_index_by_id = {str(item["probe_id"]): index for index, item in enumerate(window_rows)}
    sample_rate_hz = int(dataset["capture"]["sample_rate_hz"])
    alias_spacing_hz = float(dataset["alias_collapse"]["alias_spacing_hz"])
    _positive(alias_spacing_hz, "raw alias spacing")

    detections_by_sample: dict[int, dict[str, Any]] = {}
    for detection in scan.get("detections", ()):
        sample_start = int(detection["sample_start"])
        if sample_start in detections_by_sample:
            raise ValueError("raw pilot scan has duplicate detection sample starts")
        detections_by_sample[sample_start] = detection
    scheduled_product_starts = [int(item["sample_start"]) for item in schedule.get("probes", ())]
    if len(set(scheduled_product_starts)) != len(scheduled_product_starts):
        raise ValueError("raw probe schedule has duplicate sample starts")
    if set(detections_by_sample) != set(scheduled_product_starts):
        raise ValueError("raw pilot scan does not exactly cover its probe schedule")

    core_candidates: list[CfoCandidate] = []
    raw_observations: list[_RawObservation] = []
    group_ids: set[str] = set()
    positive_group_ids: set[str] = set()
    modeled_group_ids: set[str] = set()
    unsupported_positive_group_ids: set[str] = set()
    clutter_cost_by_group: dict[str, float] = {}
    positive_candidate_count = 0
    unsupported_positive_candidate_count = 0
    source_candidate_count = 0
    returned_candidate_count = 0
    saturated_probe_count = 0
    local_offsets_s: list[float] = []
    for sample_start, schedule_row in schedule_by_sample.items():
        detection = detections_by_sample.get(sample_start)
        expected_returned = int(schedule_row["retained_candidate_count"])
        expected_source = int(schedule_row["source_candidate_count"])
        expected_truncated = int(schedule_row["truncated_candidate_count"])
        if expected_truncated != 0:
            raise ValueError("raw replay refuses a truncated candidate inventory")
        if detection is None:
            raise ValueError("raw pilot scan does not cover every scheduled probe in the window")
        if not bool(schedule_row["scan_detection_present"]):
            raise ValueError("raw scan contains a detection omitted by duration input")
        if not math.isclose(
            float(detection["time_s"]),
            float(schedule_row["probe_start_time_s"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("raw detection time disagrees with its scheduled probe")
        status = str(detection["status"])
        if status != str(schedule_row["scan_status"]):
            raise ValueError("raw detection status disagrees with duration input")
        candidates = list(detection.get("candidates", ()))
        source_count = int(detection.get("source_candidate_count", len(candidates)))
        truncated_count = int(detection.get("truncated_candidate_count", 0))
        if truncated_count != 0 or source_count != len(candidates):
            raise ValueError("raw replay refuses truncated or inconsistent pilot candidates")
        if len(candidates) != expected_returned or source_count != expected_source:
            raise ValueError("raw candidate accounting disagrees with duration input")
        if status == "no_result" and candidates:
            raise ValueError("a no-result raw detection cannot carry candidates")
        if status == "complete" and not candidates:
            raise ValueError("a complete raw detection must carry candidates")
        if status not in {"complete", "no_result", "insufficient", "insufficient_data"}:
            raise ValueError("raw pilot detection has an unknown status")
        if status in {"insufficient", "insufficient_data"} and candidates:
            raise ValueError("an unusable raw detection cannot carry activity candidates")
        expected_usable = status in {"complete", "no_result"}
        if bool(schedule_row["usable_for_activity"]) != expected_usable:
            raise ValueError("raw detection status disagrees with scheduled-probe usability")
        source_candidate_count += source_count
        returned_candidate_count += len(candidates)
        if len(candidates) == int(scan["maximum_scored_candidates_per_probe"]):
            saturated_probe_count += 1

        rows = []
        for expected_rank, candidate in enumerate(candidates):
            rank = int(candidate["rank"])
            if rank != expected_rank:
                raise ValueError("raw pilot candidate ranks are not contiguous from zero")
            score = _glrt_score(candidate)
            cfo_hz = float(score["tracking_cfo_hz"])
            acquired_cfo_hz = float(candidate["acquired_cfo_hz"])
            residual_cfo_hz = float(score["residual_cfo_hz"])
            if not math.isclose(
                cfo_hz,
                acquired_cfo_hz + residual_cfo_hz,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("raw GLRT64 tracking CFO disagrees with acquired plus residual")
            margin = float(score["margin"])
            local_epoch_sample = int(candidate["local_epoch_sample"])
            if not 0 <= local_epoch_sample < int(schedule_row["probe_sample_count"]):
                raise ValueError("raw candidate local epoch lies outside its probe")
            local_offset_s = local_epoch_sample / sample_rate_hz
            observation_id = canonical_digest(
                {
                    "sample_start": sample_start,
                    "candidate_rank": rank,
                    "method": "glrt64",
                }
            )
            rows.append(
                {
                    "observation_id": observation_id,
                    "acquired_cfo_hz": acquired_cfo_hz,
                    "cfo_hz": cfo_hz,
                    "margin": margin,
                    "rank": rank,
                    "local_epoch_sample": local_epoch_sample,
                    "local_epoch_offset_s": local_offset_s,
                }
            )
            local_offsets_s.append(local_offset_s)

        probe_id = str(schedule_row["probe_id"])
        for row, group_id, group_margin, group_rank, group_member_count in _exclusion_groups(
            rows,
            probe_id=probe_id,
            acquired_tolerance_hz=config.duplicate_cfo_tolerance_hz,
            epoch_tolerance_samples=config.resolution_epoch_tolerance_samples,
            tracking_tolerance_hz=config.resolution_tracking_cfo_tolerance_hz,
        ):
            positive = calibration.is_positive(group_margin)
            match_supported = calibration.match_supported(group_rank)
            if positive:
                positive_candidate_count += 1
                positive_group_ids.add(group_id)
                if not match_supported:
                    unsupported_positive_candidate_count += 1
                    unsupported_positive_group_ids.add(group_id)
            group_ids.add(group_id)
            clutter_cost = calibration.clutter_cost(group_margin, group_rank)
            previous_group_cost = clutter_cost_by_group.setdefault(group_id, clutter_cost)
            if previous_group_cost != clutter_cost:
                raise ValueError("raw aliases in one exclusion group have inconsistent costs")
            observation_id = str(row["observation_id"])
            if positive and match_supported:
                modeled_group_ids.add(group_id)
                core_candidates.append(
                    CfoCandidate(
                        observation_id=observation_id,
                        probe_id=probe_id,
                        exclusion_group_id=group_id,
                        cfo_hz=float(row["cfo_hz"]),
                        sigma_hz=config.cfo_sigma_hz,
                        clutter_cost=clutter_cost,
                        matched_base_cost=calibration.matched_base_cost(
                            group_margin,
                            group_rank,
                        ),
                        component_id=f"raw:{observed_digest}:glrt64:baseband-cfo",
                    )
                )
            raw_observations.append(
                _RawObservation(
                    observation_id=observation_id,
                    exclusion_group_id=group_id,
                    probe_id=probe_id,
                    probe_index=probe_index_by_id[probe_id],
                    cfo_hz=float(row["cfo_hz"]),
                    margin=group_margin,
                    rank=int(row["rank"]),
                    group_minimum_rank=group_rank,
                    group_maximum_margin=group_margin,
                    group_member_count=group_member_count,
                    local_epoch_offset_s=float(row["local_epoch_offset_s"]),
                )
            )

    missed_cost = calibration.missed_detection_cost
    probes = tuple(
        CfoProbe(
            probe_id=str(row["probe_id"]),
            time_s=float(row["probe_start_time_s"]),
            cell_index=(int(row["probe_sample_start"]) - window_start_sample)
            // window_cell_samples,
            missed_detection_cost=(missed_cost if bool(row["usable_for_activity"]) else 0.0),
            usable=bool(row["usable_for_activity"]),
        )
        for row in window_rows
    )
    problem = SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=float(window_rows[0]["probe_start_time_s"])
            - ((int(window_rows[0]["probe_sample_start"]) - window_start_sample) / sample_rate_hz),
            cell_duration_s=config.cell_duration_s,
            cell_count=window_cell_count,
            minimum_active_cells=config.minimum_active_cells,
            allow_left_censored=config.allow_left_censored,
            allow_right_censored=config.allow_right_censored,
        ),
        probes=probes,
        observations=tuple(core_candidates),
        costs=AssociationCostModel(
            satellite_cost=config.satellite_cost,
            episode_cost=config.episode_cost,
            huber_threshold=config.huber_threshold,
        ),
        truncated_observation_count=0,
    )
    return _RawInventory(
        problem=problem,
        observations=tuple(
            sorted(raw_observations, key=lambda item: (item.probe_index, item.observation_id))
        ),
        source_candidate_count=source_candidate_count,
        returned_candidate_count=returned_candidate_count,
        exclusion_group_count=len(group_ids),
        positive_candidate_count=positive_candidate_count,
        positive_exclusion_group_count=len(positive_group_ids),
        modeled_exclusion_group_count=len(modeled_group_ids),
        unsupported_positive_candidate_count=unsupported_positive_candidate_count,
        unsupported_positive_exclusion_group_count=len(unsupported_positive_group_ids),
        dominated_weak_candidate_count=(returned_candidate_count - positive_candidate_count),
        dominated_weak_exclusion_group_count=len(group_ids - positive_group_ids),
        elided_clutter_constant=math.fsum(
            clutter_cost_by_group[group_id] for group_id in sorted(group_ids - modeled_group_ids)
        ),
        saturated_probe_count=saturated_probe_count,
        local_epoch_min_s=min(local_offsets_s) if local_offsets_s else None,
        local_epoch_max_s=max(local_offsets_s) if local_offsets_s else None,
        scan_path=scan_path.resolve(),
        scan_digest=observed_digest,
    )


def _offset_modes(
    *,
    raw: tuple[_RawObservation, ...],
    base_prediction_hz: np.ndarray,
    calibration: ScoreCalibration,
    config: RawReplayConfig,
) -> tuple[_OffsetMode, ...]:
    positive = tuple(
        item
        for item in raw
        if calibration.is_positive(item.margin)
        and calibration.match_supported(item.group_minimum_rank)
    )
    if not positive:
        return (_OffsetMode(0.0, 0, 0),)
    residual = np.asarray(
        [item.cfo_hz - base_prediction_hz[item.probe_index] for item in positive],
        dtype=np.float64,
    )
    bucket_groups: dict[int, set[str]] = defaultdict(set)
    for item, value in zip(positive, residual, strict=True):
        bucket_groups[math.floor(float(value) / config.mode_bin_hz)].add(item.exclusion_group_id)
    radius = math.ceil(config.mode_half_width_hz / config.mode_bin_hz)
    candidate_centers: set[int] = set()
    for bucket in bucket_groups:
        candidate_centers.update(range(bucket - radius, bucket + radius + 1))
    scored = []
    probe_by_group = {item.exclusion_group_id: item.probe_id for item in positive}
    for center_bucket in candidate_centers:
        groups: set[str] = set()
        for bucket in range(center_bucket - radius, center_bucket + radius + 1):
            groups.update(bucket_groups.get(bucket, ()))
        probes = {probe_by_group[group] for group in groups}
        scored.append((-len(probes), -len(groups), center_bucket))
    scored.sort()

    modes: list[_OffsetMode] = []
    for _negative_probes, _negative_groups, center_bucket in scored:
        initial = (center_bucket + 0.5) * config.mode_bin_hz
        if any(abs(initial - item.cfo_offset_hz) <= config.mode_half_width_hz for item in modes):
            continue
        best_by_probe: dict[str, tuple[float, str, str]] = {}
        for item, value in zip(positive, residual, strict=True):
            distance = abs(float(value) - initial)
            if distance > config.mode_half_width_hz:
                continue
            current = best_by_probe.get(item.probe_id)
            key = (distance, item.observation_id, item.exclusion_group_id)
            if current is None or key < current:
                best_by_probe[item.probe_id] = key
        observation_index = {item.observation_id: index for index, item in enumerate(positive)}
        selected_values = []
        selected_probes = set()
        selected_groups = set()
        for probe_id, (_distance, observation_id, group_id) in best_by_probe.items():
            index = observation_index[observation_id]
            selected_values.append(float(residual[index]))
            selected_probes.add(probe_id)
            selected_groups.add(group_id)
        if not selected_values:
            continue
        offset = float(np.median(np.asarray(selected_values, dtype=np.float64)))
        modes.append(
            _OffsetMode(
                cfo_offset_hz=offset,
                support_group_count=len(selected_groups),
                support_probe_count=len(selected_probes),
            )
        )
        if len(modes) >= config.modes_per_delay:
            break
    if not modes:
        return (_OffsetMode(0.0, 0, 0),)
    return tuple(modes)


def _state_sort_key(item: _StateEvaluation) -> tuple[object, ...]:
    return (
        item.single_total_cost,
        not item.single_selected,
        -item.proposal.support_probe_count,
        abs(item.hypothesis.delay_s),
        abs(item.hypothesis.cfo_offset_hz),
        item.hypothesis.hypothesis_id,
    )


def _catalog_state_bank(
    *,
    catalogue: Any,
    catalog_number: int,
    problem: SatelliteActivityProblem,
    raw_observations: tuple[_RawObservation, ...],
    scheduled_times_s: tuple[float, ...],
    first_sample_utc_ns: int,
    sky_frequency_hz: float,
    observer: ObserverSiteV1,
    calibration: ScoreCalibration,
    config: RawReplayConfig,
) -> tuple[tuple[_StateEvaluation, ...], tuple[_StateEvaluation, ...]]:
    satellite_index = _unique_satellite_index(catalogue, catalog_number)
    object_name = str(catalogue.names[satellite_index])
    generated = []
    for delay_s in config.delay_grid:
        curve, elevation, _altitude = _doppler_curve(
            catalogue=catalogue,
            satellite_index=satellite_index,
            first_sample_utc_ns=first_sample_utc_ns,
            scheduled_times_s=scheduled_times_s,
            delay_s=delay_s,
            sky_frequency_hz=sky_frequency_hz,
            observer=observer,
        )
        minimum_elevation = float(np.min(elevation))
        maximum_elevation = float(np.max(elevation))
        if minimum_elevation <= config.horizon_mask_deg:
            raise ValueError(
                f"NORAD {catalog_number} falls at or below the full-window horizon gate"
            )
        for mode in _offset_modes(
            raw=raw_observations,
            base_prediction_hz=curve,
            calibration=calibration,
            config=config,
        ):
            delay_prior_cost = (
                0.5 * ((delay_s - config.delay_prior_mean_s) / config.delay_prior_sigma_s) ** 2
            )
            hypothesis_id = canonical_digest(
                {
                    "catalog_number": catalog_number,
                    "delay_s": delay_s,
                    "cfo_offset_hz": mode.cfo_offset_hz,
                    "prediction_epoch": "scheduled_probe_start",
                }
            )
            hypothesis = SingleSatelliteHypothesis(
                hypothesis_id=hypothesis_id,
                object_name=object_name,
                catalog_number=catalog_number,
                delay_s=delay_s,
                cfo_offset_hz=mode.cfo_offset_hz,
                delay_prior_cost=delay_prior_cost,
                predictions=tuple(
                    PredictedProbeCfo(
                        probe_id=probe.probe_id,
                        cfo_hz=float(curve[index]),
                    )
                    for index, probe in enumerate(problem.probes)
                ),
            )
            single = decode_single_satellite(problem, hypothesis)
            generated.append(
                _StateEvaluation(
                    hypothesis=hypothesis,
                    proposal=mode,
                    single_total_cost=single.objective.total_cost,
                    single_delta_from_null=(
                        single.objective.total_cost - single.objective.null_cost
                    ),
                    single_selected=single.selected,
                    minimum_elevation_deg=minimum_elevation,
                    maximum_elevation_deg=maximum_elevation,
                )
            )
    ordered = tuple(sorted(generated, key=_state_sort_key))
    retained = ordered[: config.retained_states_per_catalog]
    if not retained:
        raise RuntimeError(f"NORAD {catalog_number} generated no nuisance states")
    return ordered, retained


def _serialize_state(
    item: _StateEvaluation,
    *,
    retained: bool,
    config: RawReplayConfig,
) -> dict[str, Any]:
    return {
        "hypothesis_id": item.hypothesis.hypothesis_id,
        "catalog_number": item.hypothesis.catalog_number,
        "object_name": item.hypothesis.object_name,
        "delay_s": item.hypothesis.delay_s,
        "cfo_offset_hz": item.hypothesis.cfo_offset_hz,
        "delay_prior_cost": item.hypothesis.delay_prior_cost,
        "mode_support_group_count": item.proposal.support_group_count,
        "mode_support_probe_count": item.proposal.support_probe_count,
        "single_satellite_selected": item.single_selected,
        "single_satellite_total_cost": item.single_total_cost,
        "single_satellite_delta_from_null": item.single_delta_from_null,
        "minimum_elevation_deg": item.minimum_elevation_deg,
        "maximum_elevation_deg": item.maximum_elevation_deg,
        "delay_at_lower_grid_boundary": math.isclose(
            item.hypothesis.delay_s,
            config.delay_min_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "delay_at_upper_grid_boundary": math.isclose(
            item.hypothesis.delay_s,
            config.delay_max_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "retained_for_grouped_search": retained,
    }


def replay_raw_window(
    *,
    dataset: dict[str, Any],
    dataset_path: Path,
    calibration_document: dict[str, Any],
    calibration_path: Path,
    tle_path: Path,
    expected_tle_digest: str,
    catalog_numbers: tuple[int, ...],
    start_s: float,
    end_s: float,
    observer: ObserverSiteV1,
    config: RawReplayConfig,
) -> dict[str, Any]:
    """Build, propose, exactly decode, and serialize one bounded raw replay."""

    if dataset.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"expected input schema {INPUT_SCHEMA}")
    if dataset.get("per_probe_rows_omitted"):
        raise ValueError("raw replay requires the full scheduled-probe extraction")
    if not 2 <= len(catalog_numbers) <= 3 or len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError("raw grouped replay requires two or three unique catalogue objects")
    _validate_calibration_grouping(calibration_document, config)
    calibration = _score(calibration_document)
    if not calibration.weak_match_is_dominated_by_miss():
        raise ValueError("score calibration does not make weak raw candidates miss-dominated")
    calibration_schema = calibration_document.get("schema")
    resolution_group_calibration = calibration_schema in {
        CALIBRATION_SCHEMA_V2,
        CALIBRATION_SCHEMA_V3,
    }
    conservative_rank_mark_calibration = calibration_schema == CALIBRATION_SCHEMA_V3

    observed_tle_digest = _file_digest(tle_path)
    if observed_tle_digest != expected_tle_digest:
        raise ValueError("raw replay TLE digest mismatch")
    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))

    ordered_schedule = _ordered_schedule(dataset)
    window_config = _WindowConfig(
        cell_duration_s=config.cell_duration_s,
        minimum_active_duration_s=config.minimum_active_duration_s,
        allow_left_censored=config.allow_left_censored,
        allow_right_censored=config.allow_right_censored,
    )
    window = _window_inventory(
        dataset=dataset,
        ordered_schedule=ordered_schedule,
        start_s=start_s,
        end_s=end_s,
        config=window_config,
    )
    inventory = _load_raw_inventory(
        dataset=dataset,
        window_rows=window.rows,
        window_start_sample=window.start_sample,
        window_cell_samples=window.cell_samples,
        window_cell_count=window.cell_count,
        calibration=calibration,
        config=config,
    )
    calibration_sources = calibration_document.get("sources", {})
    source_digests: set[str] = set()
    if isinstance(calibration_sources, dict):
        for item in calibration_sources.get("null", ()):
            if isinstance(item, dict):
                source_digests.add(str(item.get("file_digest", "")))
        for item in calibration_sources.get("signal", ()):
            if isinstance(item, dict) and isinstance(item.get("pilot_scan"), dict):
                source_digests.add(str(item["pilot_scan"].get("file_digest", "")))
    if inventory.scan_digest in source_digests:
        raise ValueError("evaluated raw scan was also used to calibrate detector-score costs")

    scheduled_times_s = tuple(float(item["probe_start_time_s"]) for item in window.rows)
    first_sample_utc_ns = int(dataset["timing_binding"]["first_estimate_utc_ns"])
    sky_frequency_hz = float(dataset["frequency_binding"]["sky_frequency_hz"])
    generated_by_catalog: dict[int, tuple[_StateEvaluation, ...]] = {}
    retained_by_catalog: dict[int, tuple[_StateEvaluation, ...]] = {}
    for catalog_number in sorted(catalog_numbers):
        generated, retained = _catalog_state_bank(
            catalogue=catalogue,
            catalog_number=catalog_number,
            problem=inventory.problem,
            raw_observations=inventory.observations,
            scheduled_times_s=scheduled_times_s,
            first_sample_utc_ns=first_sample_utc_ns,
            sky_frequency_hz=sky_frequency_hz,
            observer=observer,
            calibration=calibration,
            config=config,
        )
        generated_by_catalog[catalog_number] = generated
        retained_by_catalog[catalog_number] = retained
    retained_hypotheses = tuple(
        item.hypothesis
        for catalog_number in sorted(retained_by_catalog)
        for item in retained_by_catalog[catalog_number]
    )
    grouped = decode_grouped_nuisance_states(
        inventory.problem,
        retained_hypotheses,
        maximum_state_combinations=config.maximum_state_combinations,
    )

    selected_ids = set(grouped.selected_hypothesis_ids)
    state_by_id = {
        item.hypothesis.hypothesis_id: item
        for values in generated_by_catalog.values()
        for item in values
    }
    predictions = {}
    assignment_details = {}
    probe_time_by_id = {
        str(item["probe_id"]): float(item["probe_start_time_s"]) for item in window.rows
    }
    raw_by_id = {item.observation_id: item for item in inventory.observations}
    decision_by_id = {
        item.hypothesis_id: item for item in grouped.association.satellites if item.selected
    }
    for hypothesis_id in sorted(selected_ids):
        hypothesis = state_by_id[hypothesis_id].hypothesis
        geometric_by_probe = {item.probe_id: item.cfo_hz for item in hypothesis.predictions}
        predictions[hypothesis_id] = [
            {
                "probe_id": item.probe_id,
                "time_s": probe_time_by_id[item.probe_id],
                "predicted_cfo_hz": item.cfo_hz + hypothesis.cfo_offset_hz,
                "geometric_doppler_hz": item.cfo_hz,
            }
            for item in hypothesis.predictions
        ]
        assignment_details[hypothesis_id] = [
            {
                "probe_id": assignment.probe_id,
                "observation_id": assignment.observation_id,
                "exclusion_group_id": raw_by_id[assignment.observation_id].exclusion_group_id,
                "time_s": probe_time_by_id[assignment.probe_id],
                "observed_cfo_hz": raw_by_id[assignment.observation_id].cfo_hz,
                "predicted_cfo_hz": (
                    geometric_by_probe[assignment.probe_id] + hypothesis.cfo_offset_hz
                ),
                "residual_hz": (
                    raw_by_id[assignment.observation_id].cfo_hz
                    - geometric_by_probe[assignment.probe_id]
                    - hypothesis.cfo_offset_hz
                ),
                "glrt64_margin": raw_by_id[assignment.observation_id].margin,
                "candidate_rank": raw_by_id[assignment.observation_id].rank,
                "group_minimum_rank": raw_by_id[assignment.observation_id].group_minimum_rank,
                "group_maximum_margin": raw_by_id[assignment.observation_id].group_maximum_margin,
                "group_member_count": raw_by_id[assignment.observation_id].group_member_count,
                "local_epoch_offset_s": raw_by_id[assignment.observation_id].local_epoch_offset_s,
            }
            for assignment in decision_by_id[hypothesis_id].assignments
        ]

    retained_ids = {
        item.hypothesis.hypothesis_id for values in retained_by_catalog.values() for item in values
    }
    local_max_abs = max(
        abs(inventory.local_epoch_min_s or 0.0),
        abs(inventory.local_epoch_max_s or 0.0),
    )
    grouped_document = asdict(grouped)
    grouped_document["association"]["selected_catalog_numbers"] = list(
        grouped.association.selected_catalog_numbers
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "catalogue_search_performed": False,
        "unknown_satellite_count_solved": False,
        "conditional_on_explicit_catalog_shortlist": True,
        "conditional_on_raw_glrt64_inventory": True,
        "conditional_on_pruned_nuisance_state_bank": True,
        "costs_calibrated": False,
        "detector_score_costs_empirically_calibrated": False,
        "pooled_candidate_row_score_frequency_estimated": (not resolution_group_calibration),
        "resolution_group_score_frequency_estimated": resolution_group_calibration,
        "conservative_rank_mark_bounds_applied": conservative_rank_mark_calibration,
        "structural_costs_calibrated": False,
        "input": {
            "duration_dataset_path": str(dataset_path.resolve()),
            "duration_dataset_digest": _file_digest(dataset_path),
            "pilot_scan_path": str(inventory.scan_path),
            "pilot_scan_digest": inventory.scan_digest,
            "score_calibration_path": str(calibration_path.resolve()),
            "score_calibration_digest": _file_digest(calibration_path),
            "tle_path": str(tle_path.resolve()),
            "tle_digest": observed_tle_digest,
        },
        "window": {
            "start_s": start_s,
            "end_s": end_s,
            "cell_duration_s": config.cell_duration_s,
            "cell_count": window.cell_count,
            "minimum_active_cells": config.minimum_active_cells,
            "minimum_active_duration_s": config.minimum_active_duration_s,
            "scheduled_probe_count": len(window.rows),
        },
        "raw_inventory": {
            "source_candidate_count": inventory.source_candidate_count,
            "returned_candidate_count": inventory.returned_candidate_count,
            "truncated_candidate_count": 0,
            "probe_count_at_retained_candidate_cap": inventory.saturated_probe_count,
            "declared_post_acquisition_inventory_complete": True,
            "pre_acquisition_cap_inventory_complete": False,
            "exclusion_group_count": inventory.exclusion_group_count,
            "positive_candidate_count_after_group_scoring": inventory.positive_candidate_count,
            "positive_exclusion_group_count": inventory.positive_exclusion_group_count,
            "unsupported_positive_candidate_count": (
                inventory.unsupported_positive_candidate_count
            ),
            "unsupported_positive_exclusion_group_count": (
                inventory.unsupported_positive_exclusion_group_count
            ),
            "modeled_candidate_count": inventory.problem.returned_observation_count,
            "modeled_exclusion_group_count": inventory.modeled_exclusion_group_count,
            "dominated_weak_candidate_count": inventory.dominated_weak_candidate_count,
            "dominated_weak_exclusion_group_count": (
                inventory.dominated_weak_exclusion_group_count
            ),
            "dominated_weak_candidate_elision": {
                "applied": True,
                "decision_equivalent_under_nonnegative_residual_loss": True,
                "weak_match_is_dominated_by_miss": True,
                "unsupported_positive_groups_also_elided": True,
                "omitted_clutter_objective_constant": inventory.elided_clutter_constant,
            },
            "physical_exclusion_grouping": {
                "alias_spacing_hz": float(dataset["alias_collapse"]["alias_spacing_hz"]),
                "exact_duplicate_cfo_tolerance_hz": config.duplicate_cfo_tolerance_hz,
                "exact_duplicate_refined_basins_collapsed": True,
                "resolution_epoch_tolerance_samples": (config.resolution_epoch_tolerance_samples),
                "resolution_tracking_cfo_tolerance_hz": (
                    config.resolution_tracking_cfo_tolerance_hz
                ),
                "unresolved_measurement_cells_collapsed": True,
                "resolution_cells_are_physical_source_identities": False,
                "nonidentical_integer_aliases_grouped": False,
            },
        },
        "score_calibration": asdict(calibration),
        "configuration": asdict(config),
        "observer": {**observer.model_dump(mode="json"), "capture_bound": False},
        "nuisance_state_search": {
            "generated_state_count": sum(len(item) for item in generated_by_catalog.values()),
            "retained_state_count": len(retained_hypotheses),
            "generated_state_space_exhausted": False,
            "retained_state_space_exhausted": grouped.supplied_state_space_exhausted,
            "states": [
                _serialize_state(
                    item,
                    retained=item.hypothesis.hypothesis_id in retained_ids,
                    config=config,
                )
                for catalog_number in sorted(generated_by_catalog)
                for item in generated_by_catalog[catalog_number]
            ],
        },
        "association": grouped_document,
        "full_persisted_inventory_objective": {
            "null_cost": (
                grouped.association.objective.null_cost + inventory.elided_clutter_constant
            ),
            "total_cost": (
                grouped.association.objective.total_cost + inventory.elided_clutter_constant
            ),
            "delta_from_null": grouped.association.objective.delta_from_null,
            "constant_elided_from_exact_decision_problem": (inventory.elided_clutter_constant),
        },
        "selected_predictions": predictions,
        "selected_assignment_details": assignment_details,
        "timing_approximation": {
            "candidate_local_epoch_applied": False,
            "minimum_candidate_local_epoch_offset_s": inventory.local_epoch_min_s,
            "maximum_candidate_local_epoch_offset_s": inventory.local_epoch_max_s,
            "maximum_absolute_candidate_local_epoch_offset_s": local_max_abs,
            "prediction_epoch": "scheduled_probe_start",
        },
        "caveats": [
            "exact only over the explicit catalogue shortlist and retained nuisance-state bank",
            "nuisance proposals and pruning are data-conditioned before exact grouped decoding",
            (
                "positive score groups use worst-null-source upper intensities and "
                "simultaneous lower signal rank-mark probabilities; these remain a "
                "composite point-process pseudo-likelihood"
                if conservative_rank_mark_calibration
                else "binary score frequencies are estimated on unresolved detector-resolution "
                "groups and conditioned on coarse minimum-rank buckets, but within-probe "
                "dependence and rank-selection multiplicity remain unmodeled"
                if resolution_group_calibration
                else "binary score frequencies are pooled over candidate rows and do not "
                "model rank or within-probe group dependence"
            ),
            (
                "below-threshold and signal-rank-unsupported candidates are omitted only "
                "after preserving their clutter objective constant"
            ),
            (
                "one detector-resolution cell cannot support two independently resolved "
                "transmitters, but its members need not be one physical source"
            ),
            (
                "nonidentical raw integer aliases lack authoritative physical exclusion groups "
                "and can inflate N"
            ),
            (
                "every observed scan probe may saturate the acquisition cap despite declared "
                "truncation zero"
            ),
            "scheduled probe starts approximate candidate-specific local measurement epochs",
            "observer coordinates are explicit but not capture-bound authority",
            "no payload was decoded",
        ],
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--score-calibration", type=Path, required=True)
    parser.add_argument("--start-s", type=float, required=True)
    parser.add_argument("--end-s", type=float, required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--tle-sha256", required=True)
    parser.add_argument(
        "--catalog-number",
        action="append",
        type=int,
        required=True,
        help="repeat for exactly two or three already-gated candidates",
    )
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--cell-duration-s", type=float, default=0.1)
    parser.add_argument("--minimum-active-duration-s", type=float, default=0.5)
    parser.add_argument("--allow-left-censored", action="store_true")
    parser.add_argument("--allow-right-censored", action="store_true")
    parser.add_argument("--cfo-sigma-hz", type=float, default=100.0)
    parser.add_argument("--satellite-cost", type=float, default=5.25)
    parser.add_argument("--episode-cost", type=float, default=5.75)
    parser.add_argument("--huber-threshold", type=float, default=1.345)
    parser.add_argument("--delay-min-s", type=float, default=-2.0)
    parser.add_argument("--delay-max-s", type=float, default=2.0)
    parser.add_argument("--delay-step-s", type=float, default=0.1)
    parser.add_argument("--delay-prior-mean-s", type=float, default=0.0)
    parser.add_argument("--delay-prior-sigma-s", type=float, default=0.5)
    parser.add_argument("--duplicate-cfo-tolerance-hz", type=float, default=0.0)
    parser.add_argument("--resolution-epoch-tolerance-samples", type=int, default=1)
    parser.add_argument("--resolution-tracking-cfo-tolerance-hz", type=float, default=500.0)
    parser.add_argument("--mode-bin-hz", type=float, default=100.0)
    parser.add_argument("--mode-half-width-hz", type=float, default=300.0)
    parser.add_argument("--modes-per-delay", type=int, default=2)
    parser.add_argument("--retained-states-per-catalog", type=int, default=4)
    parser.add_argument("--maximum-state-combinations", type=int, default=256)
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    expected_tle_digest = str(arguments.tle_sha256)
    if not expected_tle_digest.startswith("sha256:"):
        expected_tle_digest = f"sha256:{expected_tle_digest}"
    config = RawReplayConfig(
        cell_duration_s=arguments.cell_duration_s,
        minimum_active_duration_s=arguments.minimum_active_duration_s,
        allow_left_censored=arguments.allow_left_censored,
        allow_right_censored=arguments.allow_right_censored,
        cfo_sigma_hz=arguments.cfo_sigma_hz,
        satellite_cost=arguments.satellite_cost,
        episode_cost=arguments.episode_cost,
        huber_threshold=arguments.huber_threshold,
        delay_min_s=arguments.delay_min_s,
        delay_max_s=arguments.delay_max_s,
        delay_step_s=arguments.delay_step_s,
        delay_prior_mean_s=arguments.delay_prior_mean_s,
        delay_prior_sigma_s=arguments.delay_prior_sigma_s,
        duplicate_cfo_tolerance_hz=arguments.duplicate_cfo_tolerance_hz,
        resolution_epoch_tolerance_samples=arguments.resolution_epoch_tolerance_samples,
        resolution_tracking_cfo_tolerance_hz=(arguments.resolution_tracking_cfo_tolerance_hz),
        mode_bin_hz=arguments.mode_bin_hz,
        mode_half_width_hz=arguments.mode_half_width_hz,
        modes_per_delay=arguments.modes_per_delay,
        retained_states_per_catalog=arguments.retained_states_per_catalog,
        maximum_state_combinations=arguments.maximum_state_combinations,
        horizon_mask_deg=arguments.horizon_mask_deg,
    )
    document = replay_raw_window(
        dataset=_read_json(arguments.input),
        dataset_path=arguments.input,
        calibration_document=_read_json(arguments.score_calibration),
        calibration_path=arguments.score_calibration,
        tle_path=arguments.tle,
        expected_tle_digest=expected_tle_digest,
        catalog_numbers=tuple(arguments.catalog_number),
        start_s=arguments.start_s,
        end_s=arguments.end_s,
        observer=ObserverSiteV1(
            latitude_deg=arguments.observer_latitude_deg,
            longitude_deg=arguments.observer_longitude_deg,
            altitude_m=arguments.observer_altitude_m,
            label=arguments.observer_label,
        ),
        config=config,
    )
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        _refuse_qnap_output(arguments.output)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
