"""Pure scoring and response-sealed satellite association for the final holdout.

The functions in this module own no filesystem, IQ reader, catalogue, or plotting
access.  The pre-response stage freezes 20 ms bin membership and every candidate
fit using strict-past even-Qin forecasts.  A later stage may attach odd-Qin values
to the already frozen bins, but cannot refit offsets, rates, identities, or masks.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256

import numpy as np
from numpy.typing import NDArray

from leo.analysis.research.doppler_holdout_pre_response import (
    DopplerHoldoutPredictionLedgerV1,
    ForecastMethod,
)
from leo.analysis.research.doppler_holdout_response_v2 import (
    OddQinAttachmentLedgerV2,
    OddQinResponseMeasurementV2,
)

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

BIN_WIDTH_NS = 20_000_000
TRAINING_FRACTION = 0.60
MINIMUM_TOTAL_BINS = 10
MINIMUM_TRAINING_BINS = 6
MINIMUM_EVALUATION_BINS = 4
MINIMUM_VISIBLE_CANDIDATES = 2
MINIMUM_ODD_BIN_FRACTION = 0.50
MAXIMUM_RATE_SENSITIVITY_HZ_S = 150.0
PRIMARY_ASSOCIATION_METHOD: ForecastMethod = "lean_500ms_quadratic"
BASELINE_ASSOCIATION_METHOD: ForecastMethod = "fixed_500ms_linear"
WRONG_TIME_OFFSETS_S = tuple(float(value) for value in range(-18_000, 0, 900)) + tuple(
    float(value) for value in range(900, 18_001, 900)
)
WITHIN_TRACK_PERMUTATION_COUNT = 20
WITHIN_TRACK_PERMUTATION_SEED = 20_260_826
ROLLING_ORIGIN_TRAINING_FRACTIONS = (0.40, 0.60, 0.80)


@dataclass(frozen=True, slots=True)
class FrozenAssociationBin:
    """One response-independent 20 ms bin."""

    session_id: str
    bin_id: int
    center_utc_ns: int
    target_count: int
    target_frame_start_samples: tuple[int, ...]
    primary_cfo_hz: float
    baseline_cfo_hz: float
    split: str


@dataclass(frozen=True, slots=True)
class FrozenCaptureBinInventory:
    """Complete bin inventory, including captures that fail support."""

    session_id: str
    prediction_ledger_digest: str
    bins: tuple[FrozenAssociationBin, ...]
    evaluable: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FrozenOddBinResponse:
    """Status-complete odd response reduction for one pre-frozen bin."""

    bin_id: int
    target_count: int
    eligible_count: int
    boundary_count: int
    no_support_count: int
    missing_count: int
    median_eligible_cfo_hz: float | None


@dataclass(frozen=True, slots=True)
class CandidateNuisanceFit:
    candidate_id: str
    training_rms_hz: float
    offset_hz: float
    rate_departure_hz_s: float
    rank: int


@dataclass(frozen=True, slots=True)
class FrozenCandidateRanking:
    """All identity and nuisance choices fixed before odd-Qin access."""

    session_id: str
    lane: str
    candidate_ids: tuple[str, ...]
    candidate_prediction_hz: tuple[tuple[float, ...], ...]
    fits: tuple[CandidateNuisanceFit, ...]
    training_bin_ids: tuple[int, ...]
    evaluation_bin_ids: tuple[int, ...]
    response_accessed: bool = False


@dataclass(frozen=True, slots=True)
class FrozenWithinTrackPermutationControl:
    """One deterministic, capture-local permutation of predictor training bins."""

    control_id: str
    permutation_index: int
    seed: int
    lane: str
    inventory: FrozenCaptureBinInventory


@dataclass(frozen=True, slots=True)
class FrozenRollingOriginControl:
    """One predictor-only split anchored to the complete frozen target span."""

    control_id: str
    training_fraction: float
    split_cutoff_utc_ns: int
    target_span_start_utc_ns: int
    target_span_stop_utc_ns: int
    inventory: FrozenCaptureBinInventory


@dataclass(frozen=True, slots=True)
class SharedRadioRateSensitivity:
    """Post-ranking, pre-response nuisance sensitivity on frozen winners only."""

    physical_radio_ids: tuple[str, ...]
    rate_departures_hz_s: tuple[float, ...]
    capture_ids: tuple[str, ...]
    capture_offsets_hz: tuple[float, ...]
    penalized_training_rms_hz: float
    rate_prior_sigma_hz_s: float = 50.0
    maximum_rate_hz_s: float = MAXIMUM_RATE_SENSITIVITY_HZ_S
    may_change_candidate_identity: bool = False


@dataclass(frozen=True, slots=True)
class CandidateResponseScore:
    candidate_id: str
    rank: int
    training_rms_hz: float
    heldout_odd_rms_hz: float | None
    heldout_finite_bin_count: int


@dataclass(frozen=True, slots=True)
class CaptureAssociationScore:
    session_id: str
    lane: str
    scores: tuple[CandidateResponseScore, ...]
    recovered_track: bool
    catalog_compatible: bool
    preset_conditional: bool
    absolute_secure_norad: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaptureForecastScore:
    session_id: str
    denominator_count: int
    prediction_complete_count: int
    response_eligible_count: int
    response_boundary_count: int
    response_no_support_count: int
    response_missing_count: int
    common_accuracy_count: int
    rms_hz: float | None
    bias_hz: float | None


@dataclass(frozen=True, slots=True)
class MethodForecastScore:
    method: ForecastMethod
    denominator_count: int
    prediction_complete_count: int
    common_accuracy_count: int
    completion_fraction: float
    equal_capture_rms_hz: float | None
    pooled_rms_hz: float | None
    captures: tuple[CaptureForecastScore, ...]


@dataclass(frozen=True, slots=True)
class QuadraticPromotionGate:
    ratio: float | None
    capture_wins: int
    capture_comparisons: int
    maximum_capture_ratio: float | None
    completion_difference_percentage_points: float
    passed: bool
    failed_conditions: tuple[str, ...]


def rounded_integer_median(values: Sequence[int]) -> int:
    """Return the exact integer median with round-to-nearest/ties-to-even.

    Converting UTC nanoseconds near 1.8e18 through float64 loses sub-128 ns
    detail.  This helper stays entirely in integer arithmetic; for an even
    cardinality it applies Python's ``round`` tie rule to the exact half-integer
    midpoint.
    """

    ordered = sorted(int(value) for value in values)
    if not ordered:
        raise ValueError("integer median requires at least one value")
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    quotient, remainder = divmod(ordered[midpoint - 1] + ordered[midpoint], 2)
    return quotient + int(remainder == 1 and quotient % 2 != 0)


def freeze_association_bins(
    ledger: DopplerHoldoutPredictionLedgerV1,
    *,
    first_sample_utc_ns: Mapping[str, int],
    sample_rate_hz: Mapping[str, int],
    bin_width_ns: int = BIN_WIDTH_NS,
) -> tuple[FrozenCaptureBinInventory, ...]:
    """Freeze bin membership from targets and forecasts, never responses.

    A bin is in the association inventory only when both the preregistered
    primary and fixed-500 baseline predictions are complete.  Every capture is
    nevertheless returned, including captures with zero evaluable bins.
    """

    if bin_width_ns != BIN_WIDTH_NS:
        raise ValueError("final association bin width is frozen at 20 ms")
    sessions = tuple(dict.fromkeys(row.target.session_id for row in ledger.rows))
    if set(sessions) != set(first_sample_utc_ns) or set(sessions) != set(sample_rate_hz):
        raise ValueError("UTC and sample-rate authorities must exactly match captures")
    output: list[FrozenCaptureBinInventory] = []
    for session_id in sessions:
        rate = sample_rate_hz[session_id]
        origin = first_sample_utc_ns[session_id]
        if rate <= 0 or origin <= 0:
            raise ValueError("association UTC authority is invalid")
        session_rows = tuple(row for row in ledger.rows if row.target.session_id == session_id)
        all_target_utc_ns = tuple(
            origin + round(row.target.reference_sample * 1_000_000_000 / rate)
            for row in session_rows
        )
        if not all_target_utc_ns:
            raise ValueError("prediction ledger contains an empty capture")
        split_cutoff_ns = min(all_target_utc_ns) + round(
            TRAINING_FRACTION * (max(all_target_utc_ns) - min(all_target_utc_ns))
        )
        groups: dict[int, list[tuple[int, int, float, float]]] = {}
        for row, utc_ns in zip(session_rows, all_target_utc_ns, strict=True):
            by_method = {forecast.method: forecast for forecast in row.forecasts}
            primary = by_method[PRIMARY_ASSOCIATION_METHOD]
            baseline = by_method[BASELINE_ASSOCIATION_METHOD]
            if primary.status != "complete" or baseline.status != "complete":
                continue
            assert primary.predicted_cfo_hz is not None
            assert baseline.predicted_cfo_hz is not None
            bin_id = utc_ns // bin_width_ns
            groups.setdefault(bin_id, []).append(
                (
                    utc_ns,
                    row.target.frame_start_sample,
                    primary.predicted_cfo_hz,
                    baseline.predicted_cfo_hz,
                )
            )
        ordered = sorted(groups.items())
        bins_list: list[FrozenAssociationBin] = []
        for bin_id, values in ordered:
            center_utc_ns = rounded_integer_median([item[0] for item in values])
            bins_list.append(
                FrozenAssociationBin(
                    session_id=session_id,
                    bin_id=bin_id,
                    center_utc_ns=center_utc_ns,
                    target_count=len(values),
                    target_frame_start_samples=tuple(item[1] for item in values),
                    primary_cfo_hz=float(np.median([item[2] for item in values])),
                    baseline_cfo_hz=float(np.median([item[3] for item in values])),
                    split="training" if center_utc_ns <= split_cutoff_ns else "evaluation",
                )
            )
        bins = tuple(bins_list)
        reasons: list[str] = []
        training_count = sum(item.split == "training" for item in bins)
        evaluation_count = sum(item.split == "evaluation" for item in bins)
        if len(bins) < MINIMUM_TOTAL_BINS:
            reasons.append("insufficient_total_bins")
        if training_count < MINIMUM_TRAINING_BINS:
            reasons.append("insufficient_training_bins")
        if evaluation_count < MINIMUM_EVALUATION_BINS:
            reasons.append("insufficient_evaluation_bins")
        output.append(
            FrozenCaptureBinInventory(
                session_id=session_id,
                prediction_ledger_digest=ledger.ledger_digest,
                bins=bins,
                evaluable=not reasons,
                failure_reasons=tuple(reasons),
            )
        )
    return tuple(output)


def frozen_wrong_time_offsets_s() -> tuple[float, ...]:
    """Return the preregistered 40-member wrong-time propagation family.

    Zero is deliberately absent: the unshifted field is the positive test, not
    one of its controls.  Keeping this family here makes it available before any
    candidate propagation or response access.
    """

    return WRONG_TIME_OFFSETS_S


def freeze_within_track_permutation_controls(
    inventory: FrozenCaptureBinInventory,
    *,
    lane: str = PRIMARY_ASSOCIATION_METHOD,
) -> tuple[FrozenWithinTrackPermutationControl, ...]:
    """Freeze 20 capture-local permutations of predictor training values.

    Only values in the requested training lane move.  Evaluation values, the
    other predictor lane, bin membership, target membership, and split labels
    are bit-for-bit unchanged.  The per-control generator seed is derived from
    the public base seed, capture identifier, lane, and permutation index so a
    caller's capture iteration order cannot affect the controls.
    """

    _validate_inventory(inventory)
    if lane not in {PRIMARY_ASSOCIATION_METHOD, BASELINE_ASSOCIATION_METHOD}:
        raise ValueError("permutation lane is not frozen")
    training_indexes = np.asarray(
        [index for index, item in enumerate(inventory.bins) if item.split == "training"],
        dtype=np.int64,
    )
    controls: list[FrozenWithinTrackPermutationControl] = []
    for permutation_index in range(WITHIN_TRACK_PERMUTATION_COUNT):
        permuted_indexes = training_indexes.copy()
        if training_indexes.size >= 2:
            material = (
                f"{WITHIN_TRACK_PERMUTATION_SEED}\x00{inventory.session_id}\x00"
                f"{lane}\x00{permutation_index}"
            ).encode()
            derived_seed = int.from_bytes(sha256(material).digest()[:16], "big")
            generator = np.random.default_rng(derived_seed)
            permuted_indexes = generator.permutation(training_indexes)
            if np.array_equal(permuted_indexes, training_indexes):
                # A null permutation is not a negative control.  The fixed roll
                # is deterministic and can only be reached for a rare identity
                # draw; it never moves values across split or capture boundaries.
                permuted_indexes = np.roll(permuted_indexes, 1)
        bins = list(inventory.bins)
        for destination, source in zip(training_indexes, permuted_indexes, strict=True):
            destination_index = int(destination)
            source_bin = inventory.bins[int(source)]
            if lane == PRIMARY_ASSOCIATION_METHOD:
                bins[destination_index] = replace(
                    bins[destination_index],
                    primary_cfo_hz=source_bin.primary_cfo_hz,
                )
            else:
                bins[destination_index] = replace(
                    bins[destination_index],
                    baseline_cfo_hz=source_bin.baseline_cfo_hz,
                )
        control_inventory = replace(inventory, bins=tuple(bins))
        _validate_control_inventory_structure(inventory, control_inventory)
        controls.append(
            FrozenWithinTrackPermutationControl(
                control_id=f"within-track-permutation-{permutation_index + 1:02d}",
                permutation_index=permutation_index,
                seed=WITHIN_TRACK_PERMUTATION_SEED,
                lane=lane,
                inventory=control_inventory,
            )
        )
    return tuple(controls)


def freeze_rolling_origin_controls(
    inventory: FrozenCaptureBinInventory,
    *,
    full_target_span_utc_ns: tuple[int, int],
) -> tuple[FrozenRollingOriginControl, ...]:
    """Freeze 40/60/80% training origins from the complete target span.

    The caller must supply the minimum and maximum UTC of *all* frozen targets,
    including targets whose forecasts were incomplete.  Consequently missing
    predictions or later odd-response availability cannot move an origin.
    Controls that miss a minimum-bin gate are returned as non-evaluable rather
    than silently dropped.
    """

    _validate_inventory(inventory)
    span_start, span_stop = full_target_span_utc_ns
    if span_start <= 0 or span_stop <= span_start:
        raise ValueError("full target UTC span must be positive and increasing")
    if any(
        item.center_utc_ns < span_start or item.center_utc_ns > span_stop for item in inventory.bins
    ):
        raise ValueError("association bin lies outside the full target UTC span")
    controls: list[FrozenRollingOriginControl] = []
    for fraction in ROLLING_ORIGIN_TRAINING_FRACTIONS:
        cutoff = span_start + round(fraction * (span_stop - span_start))
        bins = tuple(
            replace(item, split="training" if item.center_utc_ns <= cutoff else "evaluation")
            for item in inventory.bins
        )
        reasons = _inventory_support_reasons(bins)
        control_inventory = replace(
            inventory,
            bins=bins,
            evaluable=not reasons,
            failure_reasons=reasons,
        )
        _validate_control_inventory_structure(inventory, control_inventory, allow_split_change=True)
        controls.append(
            FrozenRollingOriginControl(
                control_id=f"rolling-origin-{round(100 * fraction):03d}",
                training_fraction=fraction,
                split_cutoff_utc_ns=cutoff,
                target_span_start_utc_ns=span_start,
                target_span_stop_utc_ns=span_stop,
                inventory=control_inventory,
            )
        )
    return tuple(controls)


def validate_frozen_candidate_ranking(
    ranking: FrozenCandidateRanking,
    inventory: FrozenCaptureBinInventory,
) -> None:
    """Reject any ranking that differs from its response-sealed inventory."""

    _validate_inventory(inventory)
    expected_training = tuple(item.bin_id for item in inventory.bins if item.split == "training")
    expected_evaluation = tuple(
        item.bin_id for item in inventory.bins if item.split == "evaluation"
    )
    candidate_count = len(ranking.candidate_ids)
    if ranking.session_id != inventory.session_id:
        raise ValueError("frozen ranking capture disagrees with its bin inventory")
    if ranking.lane not in {PRIMARY_ASSOCIATION_METHOD, BASELINE_ASSOCIATION_METHOD}:
        raise ValueError("frozen ranking lane is not registered")
    if ranking.response_accessed:
        raise ValueError("frozen ranking records response access")
    if (
        candidate_count < MINIMUM_VISIBLE_CANDIDATES
        or len(set(ranking.candidate_ids)) != candidate_count
        or len(ranking.candidate_prediction_hz) != candidate_count
        or len(ranking.fits) != candidate_count
        or ranking.training_bin_ids != expected_training
        or ranking.evaluation_bin_ids != expected_evaluation
        or any(len(row) != len(inventory.bins) for row in ranking.candidate_prediction_hz)
        or tuple(item.candidate_id for item in ranking.fits) != ranking.candidate_ids
        or sorted(item.rank for item in ranking.fits) != list(range(1, candidate_count + 1))
        or sum(item.rank == 1 for item in ranking.fits) != 1
    ):
        raise ValueError("frozen ranking disagrees with its bin inventory")
    if not all(
        math.isfinite(value) for candidate in ranking.candidate_prediction_hz for value in candidate
    ) or not all(
        math.isfinite(item.training_rms_hz)
        and math.isfinite(item.offset_hz)
        and item.rate_departure_hz_s == 0.0
        for item in ranking.fits
    ):
        raise ValueError("frozen ranking contains a non-finite or refit nuisance value")


def validate_frozen_capture_inventory(inventory: FrozenCaptureBinInventory) -> None:
    """Public fail-closed validation for one reloaded immutable bin inventory."""

    _validate_inventory(inventory)


def _inventory_support_reasons(
    bins: Sequence[FrozenAssociationBin],
) -> tuple[str, ...]:
    reasons: list[str] = []
    training_count = sum(item.split == "training" for item in bins)
    evaluation_count = sum(item.split == "evaluation" for item in bins)
    if len(bins) < MINIMUM_TOTAL_BINS:
        reasons.append("insufficient_total_bins")
    if training_count < MINIMUM_TRAINING_BINS:
        reasons.append("insufficient_training_bins")
    if evaluation_count < MINIMUM_EVALUATION_BINS:
        reasons.append("insufficient_evaluation_bins")
    return tuple(reasons)


def _validate_inventory(inventory: FrozenCaptureBinInventory) -> None:
    bins = inventory.bins
    if not inventory.session_id or not inventory.prediction_ledger_digest:
        raise ValueError("association inventory authority is incomplete")
    if any(
        item.session_id != inventory.session_id
        or item.target_count <= 0
        or len(item.target_frame_start_samples) != item.target_count
        or tuple(sorted(set(item.target_frame_start_samples))) != item.target_frame_start_samples
        or item.split not in {"training", "evaluation"}
        or not math.isfinite(item.primary_cfo_hz)
        or not math.isfinite(item.baseline_cfo_hz)
        for item in bins
    ):
        raise ValueError("association inventory contains an invalid bin")
    all_targets = tuple(
        frame_start for item in bins for frame_start in item.target_frame_start_samples
    )
    if (
        len(set(all_targets)) != len(all_targets)
        or len({item.bin_id for item in bins}) != len(bins)
        or any(
            left.center_utc_ns >= right.center_utc_ns
            for left, right in zip(bins, bins[1:], strict=False)
        )
    ):
        raise ValueError("association bins must be unique and time ordered")
    reasons = _inventory_support_reasons(bins)
    if inventory.failure_reasons != reasons or inventory.evaluable != (not reasons):
        raise ValueError("association inventory support accounting disagrees")


def _validate_control_inventory_structure(
    source: FrozenCaptureBinInventory,
    control: FrozenCaptureBinInventory,
    *,
    allow_split_change: bool = False,
) -> None:
    if (
        source.session_id != control.session_id
        or source.prediction_ledger_digest != control.prediction_ledger_digest
        or len(source.bins) != len(control.bins)
    ):
        raise ValueError("control inventory authority differs from its source")
    for original, changed in zip(source.bins, control.bins, strict=True):
        if (
            original.session_id != changed.session_id
            or original.bin_id != changed.bin_id
            or original.center_utc_ns != changed.center_utc_ns
            or original.target_count != changed.target_count
            or original.target_frame_start_samples != changed.target_frame_start_samples
            or (not allow_split_change and original.split != changed.split)
        ):
            raise ValueError("control inventory changed frozen target membership")
    _validate_inventory(control)


def freeze_candidate_ranking(
    inventory: FrozenCaptureBinInventory,
    *,
    lane: str,
    candidate_ids: Sequence[str],
    candidate_prediction_hz: FloatArray,
) -> FrozenCandidateRanking:
    """Fit and rank a frozen candidate matrix using predictor values only."""

    identifiers = tuple(candidate_ids)
    predictions = np.asarray(candidate_prediction_hz, dtype=np.float64)
    if len(set(identifiers)) != len(identifiers) or not identifiers:
        raise ValueError("candidate identifiers must be nonempty and unique")
    if predictions.shape != (len(identifiers), len(inventory.bins)):
        raise ValueError("candidate prediction matrix shape disagrees with frozen bins")
    if not np.all(np.isfinite(predictions)):
        raise ValueError("candidate prediction matrix must be finite")
    if lane not in {PRIMARY_ASSOCIATION_METHOD, BASELINE_ASSOCIATION_METHOD}:
        raise ValueError("association lane is not frozen")
    if not inventory.evaluable:
        raise ValueError("cannot rank candidates for a non-evaluable inventory")
    if len(identifiers) < MINIMUM_VISIBLE_CANDIDATES:
        raise ValueError("visible candidate support is below the frozen minimum")
    training = np.asarray([item.split == "training" for item in inventory.bins], dtype=bool)
    measured = np.asarray(
        [
            item.primary_cfo_hz if lane == PRIMARY_ASSOCIATION_METHOD else item.baseline_cfo_hz
            for item in inventory.bins
        ],
        dtype=float,
    )
    provisional: list[tuple[str, float, float, float]] = []
    for candidate_index, candidate_id in enumerate(identifiers):
        raw = measured - predictions[candidate_index]
        rate = 0.0
        offset = float(np.mean(raw[training]))
        residual = raw[training] - offset
        rms = float(math.sqrt(float(np.mean(residual**2))))
        provisional.append((candidate_id, rms, offset, rate))
    order = sorted(
        range(len(provisional)),
        key=lambda index: (provisional[index][1], identifiers[index]),
    )
    rank_by_index = {candidate_index: rank + 1 for rank, candidate_index in enumerate(order)}
    fits = tuple(
        CandidateNuisanceFit(
            candidate_id=item[0],
            training_rms_hz=item[1],
            offset_hz=item[2],
            rate_departure_hz_s=item[3],
            rank=rank_by_index[index],
        )
        for index, item in enumerate(provisional)
    )
    return FrozenCandidateRanking(
        session_id=inventory.session_id,
        lane=lane,
        candidate_ids=identifiers,
        candidate_prediction_hz=tuple(tuple(float(value) for value in row) for row in predictions),
        fits=fits,
        training_bin_ids=tuple(item.bin_id for item in inventory.bins if item.split == "training"),
        evaluation_bin_ids=tuple(
            item.bin_id for item in inventory.bins if item.split == "evaluation"
        ),
    )


def fit_shared_radio_rate_sensitivity(
    rankings: Sequence[FrozenCandidateRanking],
    inventories: Sequence[FrozenCaptureBinInventory],
    *,
    physical_radio_by_session: Mapping[str, str],
    measurement_scale_hz: float = 50.0,
    rate_prior_sigma_hz_s: float = 50.0,
    maximum_rate_hz_s: float = MAXIMUM_RATE_SENSITIVITY_HZ_S,
) -> SharedRadioRateSensitivity:
    """Fit shared physical-radio rates after offset-only identities are frozen.

    Candidate identity cannot change in this sensitivity.  Each capture uses its
    already frozen rank-one candidate, receives one free constant, and shares a
    zero-centered Gaussian rate departure with captures from the same radio.
    """

    if (
        measurement_scale_hz != 50.0
        or rate_prior_sigma_hz_s != 50.0
        or maximum_rate_hz_s != MAXIMUM_RATE_SENSITIVITY_HZ_S
    ):
        raise ValueError("shared-radio nuisance constants drifted")
    if not rankings or not inventories:
        raise ValueError("shared-radio sensitivity requires nonempty inventories")
    if any(item.lane != PRIMARY_ASSOCIATION_METHOD for item in rankings):
        raise ValueError("shared-radio sensitivity is frozen to the primary quadratic lane")
    if len({item.session_id for item in inventories}) != len(inventories):
        raise ValueError("shared-radio capture inventories are duplicated")
    inventory_by_session = {item.session_id: item for item in inventories}
    sessions = tuple(item.session_id for item in rankings)
    if (
        len(set(sessions)) != len(sessions)
        or set(sessions) != set(inventory_by_session)
        or set(sessions) != set(physical_radio_by_session)
    ):
        raise ValueError("shared-radio inventories disagree")
    radios = tuple(dict.fromkeys(physical_radio_by_session[item] for item in sessions))
    capture_index = {session: index for index, session in enumerate(sessions)}
    radio_index = {radio: index for index, radio in enumerate(radios)}
    design_rows: list[list[float]] = []
    values: list[float] = []
    weights: list[float] = []
    for ranking in rankings:
        inventory = inventory_by_session[ranking.session_id]
        validate_frozen_candidate_ranking(ranking, inventory)
        expected_training = tuple(
            item.bin_id for item in inventory.bins if item.split == "training"
        )
        expected_evaluation = tuple(
            item.bin_id for item in inventory.bins if item.split == "evaluation"
        )
        if (
            ranking.response_accessed
            or len(ranking.candidate_prediction_hz) != len(ranking.candidate_ids)
            or len(ranking.fits) != len(ranking.candidate_ids)
            or ranking.training_bin_ids != expected_training
            or ranking.evaluation_bin_ids != expected_evaluation
            or any(len(row) != len(inventory.bins) for row in ranking.candidate_prediction_hz)
            or tuple(item.candidate_id for item in ranking.fits) != ranking.candidate_ids
            or sorted(item.rank for item in ranking.fits) != list(range(1, len(ranking.fits) + 1))
            or sum(item.rank == 1 for item in ranking.fits) != 1
        ):
            raise ValueError("shared-radio frozen ranking disagrees with its bin inventory")
        training_indexes = [
            index for index, item in enumerate(inventory.bins) if item.split == "training"
        ]
        winner_index = next(index for index, fit in enumerate(ranking.fits) if fit.rank == 1)
        candidate = np.asarray(ranking.candidate_prediction_hz[winner_index], dtype=float)
        measured = np.asarray(
            [
                item.primary_cfo_hz
                if ranking.lane == PRIMARY_ASSOCIATION_METHOD
                else item.baseline_cfo_hz
                for item in inventory.bins
            ],
            dtype=float,
        )
        time_s = np.asarray([item.center_utc_ns for item in inventory.bins], dtype=float) * 1e-9
        local_time = time_s - float(np.mean(time_s[training_indexes]))
        row_weight = 1.0 / math.sqrt(len(training_indexes))
        for index in training_indexes:
            row = [0.0] * (len(sessions) + len(radios))
            row[capture_index[ranking.session_id]] = 1.0
            radio = physical_radio_by_session[ranking.session_id]
            row[len(sessions) + radio_index[radio]] = float(local_time[index])
            design_rows.append(row)
            values.append(float(measured[index] - candidate[index]))
            weights.append(row_weight)
    design = np.asarray(design_rows, dtype=float)
    response = np.asarray(values, dtype=float)
    weight = np.asarray(weights, dtype=float)
    penalty = measurement_scale_hz / rate_prior_sigma_hz_s
    augmented_design = np.vstack(
        [
            design * weight[:, None],
            np.column_stack(
                [
                    np.zeros((len(radios), len(sessions))),
                    np.eye(len(radios)) * penalty,
                ]
            ),
        ]
    )
    augmented_response = np.concatenate([response * weight, np.zeros(len(radios))])
    coefficients, *_ = np.linalg.lstsq(augmented_design, augmented_response, rcond=None)
    rates = np.clip(coefficients[len(sessions) :], -maximum_rate_hz_s, maximum_rate_hz_s)
    offsets = np.zeros(len(sessions), dtype=float)
    fitted = np.zeros_like(response)
    cursor = 0
    for ranking in rankings:
        inventory = inventory_by_session[ranking.session_id]
        count = sum(item.split == "training" for item in inventory.bins)
        radio = physical_radio_by_session[ranking.session_id]
        local_design = design[cursor : cursor + count]
        raw = response[cursor : cursor + count]
        rate = rates[radio_index[radio]]
        time_column = local_design[:, len(sessions) + radio_index[radio]]
        offset = float(np.mean(raw - rate * time_column))
        offsets[capture_index[ranking.session_id]] = offset
        fitted[cursor : cursor + count] = offset + rate * time_column
        cursor += count
    weighted_mse = float(np.sum(np.square((response - fitted) * weight)) / len(sessions))
    rate_penalty = float(np.sum(np.square(rates / rate_prior_sigma_hz_s)) / len(sessions))
    penalized_rms = math.sqrt(weighted_mse + measurement_scale_hz**2 * rate_penalty)
    return SharedRadioRateSensitivity(
        physical_radio_ids=radios,
        rate_departures_hz_s=tuple(float(value) for value in rates),
        capture_ids=sessions,
        capture_offsets_hz=tuple(float(value) for value in offsets),
        penalized_training_rms_hz=penalized_rms,
    )


def score_frozen_candidate_ranking(
    ranking: FrozenCandidateRanking,
    inventory: FrozenCaptureBinInventory,
    *,
    odd_response_by_bin: Mapping[int, FrozenOddBinResponse],
) -> CaptureAssociationScore:
    """Score once without refitting or changing the frozen bin denominator."""

    expected_bins = {item.bin_id for item in inventory.bins}
    if set(odd_response_by_bin) != expected_bins:
        raise ValueError("odd response inventory must retain every frozen bin")
    validate_frozen_candidate_ranking(ranking, inventory)
    predictions = np.asarray(ranking.candidate_prediction_hz, dtype=float)
    time_s = np.asarray([item.center_utc_ns for item in inventory.bins], dtype=float) * 1e-9
    training = np.asarray([item.split == "training" for item in inventory.bins], dtype=bool)
    evaluation = ~training
    reference_s = float(np.mean(time_s[training]))
    for item in inventory.bins:
        response = odd_response_by_bin[item.bin_id]
        if response.bin_id != item.bin_id or response.target_count != item.target_count:
            raise ValueError("odd bin response accounting differs from frozen membership")
        if (
            response.eligible_count
            + response.boundary_count
            + response.no_support_count
            + response.missing_count
            != response.target_count
        ):
            raise ValueError("odd bin status accounting disagrees")
        if (
            response.eligible_count > 0
            and (
                response.median_eligible_cfo_hz is None
                or not math.isfinite(response.median_eligible_cfo_hz)
            )
        ) or (response.eligible_count == 0 and response.median_eligible_cfo_hz is not None):
            raise ValueError("odd bin eligible median accounting disagrees")
    responses = np.asarray(
        [
            np.nan
            if odd_response_by_bin[item.bin_id].median_eligible_cfo_hz is None
            else odd_response_by_bin[item.bin_id].median_eligible_cfo_hz
            for item in inventory.bins
        ],
        dtype=float,
    )
    finite_evaluation = evaluation & np.isfinite(responses)
    scores: list[CandidateResponseScore] = []
    for index, fit in enumerate(ranking.fits):
        if np.any(finite_evaluation):
            predicted = (
                predictions[index]
                + fit.offset_hz
                + fit.rate_departure_hz_s * (time_s - reference_s)
            )
            rms: float | None = float(
                math.sqrt(
                    float(
                        np.mean((responses[finite_evaluation] - predicted[finite_evaluation]) ** 2)
                    )
                )
            )
        else:
            rms = None
        scores.append(
            CandidateResponseScore(
                candidate_id=fit.candidate_id,
                rank=fit.rank,
                training_rms_hz=fit.training_rms_hz,
                heldout_odd_rms_hz=rms,
                heldout_finite_bin_count=int(np.count_nonzero(finite_evaluation)),
            )
        )
    ordered = tuple(sorted(scores, key=lambda item: item.rank))
    reasons: list[str] = []
    if int(np.count_nonzero(finite_evaluation)) < MINIMUM_EVALUATION_BINS:
        reasons.append("insufficient_finite_heldout_bins")
    if int(np.count_nonzero(finite_evaluation)) < math.ceil(
        MINIMUM_ODD_BIN_FRACTION * int(np.count_nonzero(evaluation))
    ):
        reasons.append("heldout_odd_bin_availability_below_50pct")
    if len(ordered) < MINIMUM_VISIBLE_CANDIDATES:
        reasons.append("insufficient_visible_candidates")
    recovered = not reasons and all(item.heldout_odd_rms_hz is not None for item in ordered)
    # Candidate evidence is intentionally finalized by the report runner after
    # applying the frozen control families and baseline/primary agreement gates.
    return CaptureAssociationScore(
        session_id=ranking.session_id,
        lane=ranking.lane,
        scores=ordered,
        recovered_track=recovered,
        catalog_compatible=False,
        preset_conditional=False,
        absolute_secure_norad=False,
        failure_reasons=tuple(reasons) + ("control_gates_not_applied",),
    )


def aggregate_odd_responses_to_frozen_bins(
    inventory: FrozenCaptureBinInventory,
    attachment: OddQinAttachmentLedgerV2,
    *,
    first_sample_utc_ns: int,
    sample_rate_hz: int,
) -> dict[int, FrozenOddBinResponse]:
    """Reduce eligible odd CFOs without changing the pre-response bin inventory."""

    if first_sample_utc_ns <= 0 or sample_rate_hz <= 0:
        raise ValueError("odd-bin UTC authority is invalid")
    if attachment.prediction_ledger_digest != inventory.prediction_ledger_digest:
        raise ValueError("odd attachment uses another frozen prediction ledger")
    expected_bins = {item.bin_id: item for item in inventory.bins}
    selected_targets = {
        (inventory.session_id, frame_start): bin_id
        for bin_id, item in expected_bins.items()
        for frame_start in item.target_frame_start_samples
    }
    grouped: dict[int, list[OddQinResponseMeasurementV2]] = {bin_id: [] for bin_id in expected_bins}
    for row in attachment.rows:
        target_key = row.target.identity()
        if target_key not in selected_targets:
            continue
        utc_ns = first_sample_utc_ns + round(
            row.target.reference_sample * 1_000_000_000 / sample_rate_hz
        )
        bin_id = utc_ns // BIN_WIDTH_NS
        if bin_id != selected_targets[target_key]:
            raise ValueError("odd response target moved outside its frozen bin")
        grouped[bin_id].append(row.response)
    output: dict[int, FrozenOddBinResponse] = {}
    for bin_id, frozen in expected_bins.items():
        responses = grouped[bin_id]
        if len(responses) != frozen.target_count:
            raise ValueError("odd responses do not cover a frozen bin target inventory")
        statuses = [item.status for item in responses]
        eligible = [
            float(item.odd_absolute_cfo_hz)
            for item in responses
            if item.accuracy_disposition == "eligible" and item.odd_absolute_cfo_hz is not None
        ]
        output[bin_id] = FrozenOddBinResponse(
            bin_id=bin_id,
            target_count=len(responses),
            eligible_count=statuses.count("finite"),
            boundary_count=statuses.count("boundary"),
            no_support_count=statuses.count("no_support"),
            missing_count=statuses.count("missing"),
            median_eligible_cfo_hz=float(np.median(eligible)) if eligible else None,
        )
    return output


def score_forecasts(
    prediction: DopplerHoldoutPredictionLedgerV1,
    attachment: OddQinAttachmentLedgerV2,
) -> tuple[MethodForecastScore, ...]:
    """Score all methods on one common eligible response/prediction mask."""

    if attachment.prediction_ledger_digest != prediction.ledger_digest:
        raise ValueError("prediction and response ledgers disagree")
    if tuple(row.target for row in attachment.rows) != tuple(row.target for row in prediction.rows):
        raise ValueError("response target contracts differ from frozen prediction targets")
    response_by_key = {row.target.identity(): row.response for row in attachment.rows}
    if set(response_by_key) != {row.target.identity() for row in prediction.rows}:
        raise ValueError("response target inventory disagrees")
    methods = tuple(forecast.method for forecast in prediction.rows[0].forecasts)
    common_keys = {
        row.target.identity()
        for row in prediction.rows
        if response_by_key[row.target.identity()].accuracy_disposition == "eligible"
        and all(forecast.status == "complete" for forecast in row.forecasts)
    }
    sessions = tuple(dict.fromkeys(row.target.session_id for row in prediction.rows))
    output: list[MethodForecastScore] = []
    for method in methods:
        capture_scores: list[CaptureForecastScore] = []
        pooled_errors: list[float] = []
        prediction_complete = 0
        for session in sessions:
            rows = tuple(row for row in prediction.rows if row.target.session_id == session)
            errors: list[float] = []
            complete = 0
            response_eligible = 0
            response_boundary = 0
            response_no_support = 0
            response_missing = 0
            for row in rows:
                forecast = next(item for item in row.forecasts if item.method == method)
                response = response_by_key[row.target.identity()]
                complete += forecast.status == "complete"
                response_eligible += response.accuracy_disposition == "eligible"
                response_boundary += response.status == "boundary"
                response_no_support += response.status == "no_support"
                response_missing += response.status == "missing"
                if row.target.identity() in common_keys:
                    assert forecast.predicted_cfo_hz is not None
                    assert response.odd_absolute_cfo_hz is not None
                    errors.append(forecast.predicted_cfo_hz - response.odd_absolute_cfo_hz)
            prediction_complete += complete
            pooled_errors.extend(errors)
            capture_scores.append(
                CaptureForecastScore(
                    session_id=session,
                    denominator_count=len(rows),
                    prediction_complete_count=complete,
                    response_eligible_count=response_eligible,
                    response_boundary_count=response_boundary,
                    response_no_support_count=response_no_support,
                    response_missing_count=response_missing,
                    common_accuracy_count=len(errors),
                    rms_hz=(
                        float(math.sqrt(float(np.mean(np.square(errors))))) if errors else None
                    ),
                    bias_hz=float(np.mean(errors)) if errors else None,
                )
            )
        capture_mse = [item.rms_hz**2 for item in capture_scores if item.rms_hz is not None]
        output.append(
            MethodForecastScore(
                method=method,
                denominator_count=prediction.target_count,
                prediction_complete_count=prediction_complete,
                common_accuracy_count=len(common_keys),
                completion_fraction=prediction_complete / prediction.target_count,
                equal_capture_rms_hz=(
                    float(math.sqrt(float(np.mean(capture_mse)))) if capture_mse else None
                ),
                pooled_rms_hz=(
                    float(math.sqrt(float(np.mean(np.square(pooled_errors)))))
                    if pooled_errors
                    else None
                ),
                captures=tuple(capture_scores),
            )
        )
    return tuple(output)


def quadratic_promotion_gate(
    scores: Sequence[MethodForecastScore],
) -> QuadraticPromotionGate:
    """Apply the immutable four-part quadratic-versus-fixed500 gate."""

    by_method = {item.method: item for item in scores}
    baseline = by_method[BASELINE_ASSOCIATION_METHOD]
    quadratic = by_method[PRIMARY_ASSOCIATION_METHOD]
    if baseline.equal_capture_rms_hz is None or quadratic.equal_capture_rms_hz is None:
        ratio = None
    else:
        ratio = quadratic.equal_capture_rms_hz / baseline.equal_capture_rms_hz
    baseline_capture = {item.session_id: item for item in baseline.captures}
    ratios: list[float] = []
    wins = 0
    for item in quadratic.captures:
        other = baseline_capture[item.session_id]
        if item.rms_hz is None or other.rms_hz is None or other.rms_hz <= 0.0:
            continue
        local_ratio = item.rms_hz / other.rms_hz
        ratios.append(local_ratio)
        wins += local_ratio < 1.0
    completion_difference = 100.0 * abs(
        quadratic.completion_fraction - baseline.completion_fraction
    )
    failed: list[str] = []
    if ratio is None or ratio > 0.95:
        failed.append("equal_capture_rms_ratio_above_0_95")
    if wins < 8:
        failed.append("fewer_than_8_capture_wins")
    if len(ratios) != 10:
        failed.append("not_all_10_captures_compared")
    for item in quadratic.captures:
        if item.response_eligible_count < math.ceil(
            0.5 * item.denominator_count
        ) or item.common_accuracy_count < math.ceil(0.5 * item.denominator_count):
            failed.append("capture_response_availability_below_50pct")
            break
    if not ratios or max(ratios) > 1.10:
        failed.append("capture_ratio_above_1_10")
    if completion_difference > 1.0:
        failed.append("completion_difference_above_1pp")
    return QuadraticPromotionGate(
        ratio=ratio,
        capture_wins=wins,
        capture_comparisons=len(ratios),
        maximum_capture_ratio=max(ratios) if ratios else None,
        completion_difference_percentage_points=completion_difference,
        passed=not failed,
        failed_conditions=tuple(failed),
    )
