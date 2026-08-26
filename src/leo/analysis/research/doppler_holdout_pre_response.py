"""Response-sealed Doppler holdout forecasts and odd-Qin attachment contracts.

The predictor deliberately receives a target coordinate separately from the
even-Qin evidence inventory.  Every fit uses only supported rows in
``[target - horizon, target)``.  The target frame's even-Qin value can therefore
never enter a forecast, even when that row is present in the evidence tuple.

Odd-Qin extraction is represented by a narrow port.  Its request contains the
frozen acquisition trajectory center and odd symbol selection, but no target
even-Qin measurement.  The attachment operation can append responses to an
immutable prediction ledger; it cannot change target membership or forecasts.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Annotated, Literal, Protocol, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from leo.analysis.research.doppler_holdout_manifest import (
    DerivedHoldoutEpisodeV1,
    FrameMaskDispositionV1,
)
from leo.analysis.research.doppler_holdout_selector_v2 import (
    DopplerHoldoutDerivedManifestV2,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

PREDICTION_LEDGER_SCHEMA = "org.leo.research.doppler-holdout-prediction-ledger/v1"
ODD_ATTACHMENT_SCHEMA = "org.leo.research.doppler-holdout-odd-attachment/v1"
SYMBOL_ALIAS_SPACING_HZ = 1.0 / 4.4e-6

ForecastMethod = Literal[
    "fixed_20ms_linear",
    "fixed_125ms_linear",
    "fixed_500ms_linear",
    "lean_500ms_quadratic",
]
ForecastStatus = Literal["complete", "no_result"]
ResponseStatus = Literal["finite", "boundary", "no_support", "missing"]
AccuracyDisposition = Literal[
    "eligible",
    "excluded_boundary",
    "excluded_no_support",
    "missing",
]
Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
ReasonCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]


class _ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class StrictPastForecastConfigV1(_ResearchModel):
    """One fixed, response-independent robust polynomial forecast."""

    name: ForecastMethod
    history_s: Annotated[float, Field(gt=0)]
    polynomial_degree: Literal[1, 2]
    minimum_frames: Annotated[int, Field(ge=3)]
    minimum_effective_frames: Annotated[float, Field(gt=2)]
    minimum_history_coverage: Annotated[float, Field(gt=0, le=1)] = 0.95
    maximum_gap_s: Annotated[float, Field(gt=0)] = 0.1
    fixed_measurement_sigma_hz: Annotated[float, Field(gt=0)] = 50.0
    huber_tuning: Annotated[float, Field(gt=0)] = 1.345
    maximum_iterations: Annotated[int, Field(gt=0)] = 24
    prediction_convergence_hz: Annotated[float, Field(gt=0)] = 1e-6
    standardized_scale_floor: Annotated[float, Field(gt=0)] = 1.0
    maximum_normal_condition: Annotated[float, Field(gt=1)] = 1e14
    regularization: Literal["none"] = "none"

    @model_validator(mode="after")
    def _method_geometry_is_frozen(self) -> Self:
        expected = {
            "fixed_20ms_linear": (0.020, 1, 3, 3.0),
            "fixed_125ms_linear": (0.125, 1, 12, 8.0),
            "fixed_500ms_linear": (0.500, 1, 12, 8.0),
            "lean_500ms_quadratic": (0.500, 2, 24, 16.0),
        }[self.name]
        actual = (
            self.history_s,
            self.polynomial_degree,
            self.minimum_frames,
            self.minimum_effective_frames,
        )
        if actual != expected:
            raise ValueError("forecast method geometry drifted")
        if self.minimum_effective_frames > self.minimum_frames:
            raise ValueError("minimum effective frames exceed frame minimum")
        return self


DEFAULT_STRICT_PAST_CONFIGS: tuple[StrictPastForecastConfigV1, ...] = (
    StrictPastForecastConfigV1(
        name="fixed_20ms_linear",
        history_s=0.020,
        polynomial_degree=1,
        minimum_frames=3,
        minimum_effective_frames=3.0,
    ),
    StrictPastForecastConfigV1(
        name="fixed_125ms_linear",
        history_s=0.125,
        polynomial_degree=1,
        minimum_frames=12,
        minimum_effective_frames=8.0,
    ),
    StrictPastForecastConfigV1(
        name="fixed_500ms_linear",
        history_s=0.500,
        polynomial_degree=1,
        minimum_frames=12,
        minimum_effective_frames=8.0,
    ),
    StrictPastForecastConfigV1(
        name="lean_500ms_quadratic",
        history_s=0.500,
        polynomial_degree=2,
        minimum_frames=24,
        minimum_effective_frames=16.0,
    ),
)


class ForecastTargetKeyV1(_ResearchModel):
    session_id: Identifier
    episode_id: Sha256Digest
    target_mask_digest: Sha256Digest
    frame_start_sample: Annotated[int, Field(ge=1)]
    reference_sample: Annotated[float, Field(gt=0)]
    continuity_segment_id: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _reference_is_finite(self) -> Self:
        if not math.isfinite(self.reference_sample):
            raise ValueError("target reference sample must be finite")
        return self

    def identity(self) -> tuple[str, int]:
        return (self.session_id, self.frame_start_sample)


class StrictPastForecastV1(_ResearchModel):
    method: ForecastMethod
    history_s: Annotated[float, Field(gt=0)]
    polynomial_degree: Literal[1, 2]
    status: ForecastStatus
    rejection_reasons: tuple[ReasonCode, ...]
    history_frame_count: Annotated[int, Field(ge=0)]
    effective_history_frame_count: Annotated[float | None, Field(gt=0)] = None
    history_span_ms: Annotated[float, Field(ge=0)]
    history_to_target_span_ms: Annotated[float, Field(ge=0)]
    maximum_gap_ms: Annotated[float, Field(ge=0)]
    earliest_history_reference_sample: float | None = None
    latest_history_reference_sample: float | None = None
    history_digest: Sha256Digest
    predicted_cfo_hz: float | None = None
    rate_hz_s: float | None = None
    acceleration_hz_s2: float | None = None
    weighted_rms_hz: float | None = None
    converged: bool | None = None

    @model_validator(mode="after")
    def _forecast_is_closed(self) -> Self:
        finite_optional = (
            self.effective_history_frame_count,
            self.earliest_history_reference_sample,
            self.latest_history_reference_sample,
            self.predicted_cfo_hz,
            self.rate_hz_s,
            self.acceleration_hz_s2,
            self.weighted_rms_hz,
        )
        if any(value is not None and not math.isfinite(value) for value in finite_optional):
            raise ValueError("forecast value must be finite")
        estimates = (
            self.predicted_cfo_hz,
            self.rate_hz_s,
            self.acceleration_hz_s2,
            self.weighted_rms_hz,
            self.converged,
        )
        if self.status == "complete":
            if self.rejection_reasons or any(value is None for value in estimates):
                raise ValueError("complete forecast requires all estimates and no rejection")
            if self.converged is not True:
                raise ValueError("complete forecast requires a converged robust fit")
            if self.earliest_history_reference_sample is None or (
                self.latest_history_reference_sample is None
            ):
                raise ValueError("complete forecast requires strict-past history bounds")
            if self.polynomial_degree == 1 and self.acceleration_hz_s2 != 0.0:
                raise ValueError("linear forecast acceleration must be zero")
        elif not self.rejection_reasons or any(value is not None for value in estimates):
            raise ValueError("no-result forecast requires reasons and no estimates")
        return self


class PredictionLedgerRowV1(_ResearchModel):
    target: ForecastTargetKeyV1
    target_even_status_used_for_membership: Literal[True] = True
    target_even_numeric_cfo_consumed: Literal[False] = False
    forecasts: tuple[StrictPastForecastV1, ...]

    @model_validator(mode="after")
    def _methods_and_history_are_closed(self) -> Self:
        expected = tuple(item.name for item in DEFAULT_STRICT_PAST_CONFIGS)
        if tuple(item.method for item in self.forecasts) != expected:
            raise ValueError("prediction row method order or membership drifted")
        for forecast in self.forecasts:
            latest = forecast.latest_history_reference_sample
            if latest is not None and not latest < self.target.reference_sample:
                raise ValueError("forecast consumed the target or a future even-Qin value")
        return self


class DopplerHoldoutPredictionLedgerV1(_ResearchModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.doppler-holdout-prediction-ledger/v1"
    ]
    phase: Literal["pre_response_prediction_freeze"]
    source_v2_file_sha256: Sha256Digest
    source_v2_manifest_digest: Sha256Digest
    forecast_implementation_sha256: Sha256Digest
    forecast_configuration_digest: Sha256Digest
    future_odd_qin_outcomes_opened: Literal[False]
    target_even_numeric_cfo_consumed: Literal[False]
    target_count: Annotated[int, Field(gt=0)]
    rows: tuple[PredictionLedgerRowV1, ...]
    ledger_digest: Sha256Digest

    @model_validator(mode="after")
    def _ledger_is_closed(self) -> Self:
        identities = tuple(row.target.identity() for row in self.rows)
        if len(self.rows) != self.target_count or len(set(identities)) != len(identities):
            raise ValueError("prediction ledger target accounting is not closed")
        content = self.model_dump(mode="json", exclude={"ledger_digest"})
        if self.ledger_digest != canonical_digest(content):
            raise ValueError("prediction ledger digest disagrees")
        return self


def strict_past_forecasts(
    target: ForecastTargetKeyV1,
    even_rows: Sequence[FrameMaskDispositionV1],
    *,
    sample_rate_hz: int,
    configs: tuple[StrictPastForecastConfigV1, ...] = DEFAULT_STRICT_PAST_CONFIGS,
) -> tuple[StrictPastForecastV1, ...]:
    """Forecast one target without consuming its numeric even-Qin measurement."""

    if sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive")
    if tuple(config.name for config in configs) != tuple(
        config.name for config in DEFAULT_STRICT_PAST_CONFIGS
    ):
        raise ValueError("strict-past method order or membership drifted")
    starts = tuple(row.frame_start_sample for row in even_rows)
    if starts != tuple(sorted(set(starts))):
        raise ValueError("even evidence must be uniquely sample-ordered")
    references = tuple(row.reference_sample for row in even_rows)
    if references != tuple(sorted(set(references))):
        raise ValueError("even evidence references must be uniquely sample-ordered")
    return tuple(
        _forecast_one(target, even_rows, sample_rate_hz=sample_rate_hz, config=config)
        for config in configs
    )


def build_prediction_ledger(
    manifest: DopplerHoldoutDerivedManifestV2,
    *,
    source_v2_file_sha256: str,
    forecast_implementation_sha256: str,
    configs: tuple[StrictPastForecastConfigV1, ...] = DEFAULT_STRICT_PAST_CONFIGS,
) -> DopplerHoldoutPredictionLedgerV1:
    """Build an immutable even-only ledger for every frozen evaluable target."""

    rows: list[PredictionLedgerRowV1] = []
    for capture in manifest.captures:
        if capture.status != "evaluable":
            continue
        episode = capture.inherited_v1_disposition.episode
        if episode is None:
            raise ValueError("evaluable v2 capture lacks its inherited episode")
        for target in capture.target_mask:
            if target.status != "eligible":
                continue
            if target.continuity_segment_id is None:
                raise ValueError("eligible target lacks its continuity segment")
            key = ForecastTargetKeyV1(
                session_id=capture.session_id,
                episode_id=episode.episode_id,
                target_mask_digest=capture.target_mask_digest,
                frame_start_sample=target.frame_start_sample,
                reference_sample=target.reference_sample,
                continuity_segment_id=target.continuity_segment_id,
            )
            rows.append(
                PredictionLedgerRowV1(
                    target=key,
                    forecasts=strict_past_forecasts(
                        key,
                        episode.frame_mask,
                        sample_rate_hz=capture.sample_rate_hz,
                        configs=configs,
                    ),
                )
            )
    configuration_digest = canonical_digest([config.model_dump(mode="json") for config in configs])
    document = {
        "schema": PREDICTION_LEDGER_SCHEMA,
        "phase": "pre_response_prediction_freeze",
        "source_v2_file_sha256": source_v2_file_sha256,
        "source_v2_manifest_digest": manifest.manifest_digest,
        "forecast_implementation_sha256": forecast_implementation_sha256,
        "forecast_configuration_digest": configuration_digest,
        "future_odd_qin_outcomes_opened": False,
        "target_even_numeric_cfo_consumed": False,
        "target_count": len(rows),
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    return DopplerHoldoutPredictionLedgerV1.model_validate(
        {**document, "ledger_digest": canonical_digest(document)}
    )


def _forecast_one(
    target: ForecastTargetKeyV1,
    even_rows: Sequence[FrameMaskDispositionV1],
    *,
    sample_rate_hz: int,
    config: StrictPastForecastConfigV1,
) -> StrictPastForecastV1:
    lower = target.reference_sample - config.history_s * sample_rate_hz
    history = tuple(
        row
        for row in even_rows
        if row.status == "supported"
        and row.continuity_segment_id == target.continuity_segment_id
        and lower <= row.reference_sample < target.reference_sample
    )
    history_document = [
        {
            "frame_start_sample": row.frame_start_sample,
            "reference_sample": row.reference_sample,
            "even_absolute_cfo_hz": row.even_absolute_cfo_hz,
        }
        for row in history
    ]
    digest = canonical_digest(history_document)
    count = len(history)
    earliest = history[0].reference_sample if history else None
    latest = history[-1].reference_sample if history else None
    history_span_ms = (
        (history[-1].reference_sample - history[0].reference_sample) * 1_000.0 / sample_rate_hz
        if count > 1
        else 0.0
    )
    target_span_ms = (
        (target.reference_sample - history[0].reference_sample) * 1_000.0 / sample_rate_hz
        if history
        else 0.0
    )
    gaps_samples = (
        np.diff(
            np.asarray(
                [row.reference_sample for row in history] + [target.reference_sample],
                dtype=float,
            )
        )
        if history
        else np.asarray([], dtype=float)
    )
    maximum_gap_ms = (
        float(np.max(gaps_samples)) * 1_000.0 / sample_rate_hz if gaps_samples.size else 0.0
    )
    common = {
        "method": config.name,
        "history_s": config.history_s,
        "polynomial_degree": config.polynomial_degree,
        "history_frame_count": count,
        "history_span_ms": history_span_ms,
        "history_to_target_span_ms": target_span_ms,
        "maximum_gap_ms": maximum_gap_ms,
        "earliest_history_reference_sample": earliest,
        "latest_history_reference_sample": latest,
        "history_digest": digest,
    }
    reasons: list[str] = []
    if count < config.minimum_frames:
        reasons.append("insufficient_history_frames")
    if target_span_ms + 1e-9 < config.history_s * config.minimum_history_coverage * 1_000.0:
        reasons.append("insufficient_history_coverage")
    if maximum_gap_ms > config.maximum_gap_s * 1_000.0 + 1e-9:
        reasons.append("history_gap")
    if reasons:
        return StrictPastForecastV1.model_validate(
            {**common, "status": "no_result", "rejection_reasons": tuple(reasons)}
        )

    times = np.asarray(
        [(row.reference_sample - target.reference_sample) / sample_rate_hz for row in history],
        dtype=float,
    )
    values = np.asarray([_supported_even_cfo(row) for row in history], dtype=float)
    design_columns = [np.ones(count, dtype=float), times]
    if config.polynomial_degree == 2:
        design_columns.append(0.5 * times**2)
    design = np.column_stack(design_columns)
    precision = np.full(count, 1.0 / config.fixed_measurement_sigma_hz**2, dtype=float)
    normal = design.T @ (precision[:, None] * design)
    if not np.all(np.isfinite(normal)) or np.linalg.cond(normal) > config.maximum_normal_condition:
        return StrictPastForecastV1.model_validate(
            {
                **common,
                "status": "no_result",
                "rejection_reasons": ("ill_conditioned_history",),
            }
        )
    try:
        coefficients = np.linalg.solve(normal, design.T @ (precision * values))
    except np.linalg.LinAlgError:
        return StrictPastForecastV1.model_validate(
            {
                **common,
                "status": "no_result",
                "rejection_reasons": ("ill_conditioned_history",),
            }
        )

    weights = np.ones(count, dtype=float)
    converged = False
    for _ in range(config.maximum_iterations):
        residual = values - design @ coefficients
        standardized = residual / config.fixed_measurement_sigma_hz
        centered = standardized - float(np.median(standardized))
        scale = max(
            config.standardized_scale_floor,
            1.4826 * float(np.median(np.abs(centered))),
        )
        magnitude = np.abs(standardized) / scale
        weights = np.ones(count, dtype=float)
        tail = magnitude > config.huber_tuning
        weights[tail] = config.huber_tuning / magnitude[tail]
        weighted_precision = precision * weights
        normal = design.T @ (weighted_precision[:, None] * design)
        if not np.all(np.isfinite(normal)) or (
            np.linalg.cond(normal) > config.maximum_normal_condition
        ):
            return StrictPastForecastV1.model_validate(
                {
                    **common,
                    "status": "no_result",
                    "rejection_reasons": ("ill_conditioned_history",),
                }
            )
        try:
            updated = np.linalg.solve(normal, design.T @ (weighted_precision * values))
        except np.linalg.LinAlgError:
            return StrictPastForecastV1.model_validate(
                {
                    **common,
                    "status": "no_result",
                    "rejection_reasons": ("ill_conditioned_history",),
                }
            )
        prediction_change = float(np.max(np.abs(design @ (updated - coefficients))))
        coefficients = updated
        if prediction_change <= config.prediction_convergence_hz:
            converged = True
            break

    if not converged:
        return StrictPastForecastV1.model_validate(
            {
                **common,
                "status": "no_result",
                "rejection_reasons": ("fit_not_converged",),
            }
        )

    residual = values - design @ coefficients
    effective = float(np.sum(weights) ** 2 / np.sum(weights**2))
    if effective + 1e-12 < config.minimum_effective_frames:
        return StrictPastForecastV1.model_validate(
            {
                **common,
                "status": "no_result",
                "rejection_reasons": ("insufficient_effective_frames",),
            }
        )
    weighted_rms = float(math.sqrt(float(np.sum(weights * residual**2) / np.sum(weights))))
    acceleration = float(coefficients[2]) if config.polynomial_degree == 2 else 0.0
    return StrictPastForecastV1.model_validate(
        {
            **common,
            "status": "complete",
            "rejection_reasons": (),
            "effective_history_frame_count": effective,
            "predicted_cfo_hz": float(coefficients[0]),
            "rate_hz_s": float(coefficients[1]),
            "acceleration_hz_s2": acceleration,
            "weighted_rms_hz": weighted_rms,
            "converged": converged,
        }
    )


def _supported_even_cfo(row: FrameMaskDispositionV1) -> float:
    value = row.even_absolute_cfo_hz
    if value is None:
        raise ValueError("supported history row lacks an even-Qin CFO")
    return value


class OddQinTargetAuthorityV1(_ResearchModel):
    """Exact response target authority with no target-even measurement field."""

    target: ForecastTargetKeyV1
    scope_key: Sha256Digest
    stream_id: Identifier
    radio_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    edge: Literal["lower", "upper"]
    source_id: Sha256Digest
    branch_id: Sha256Digest
    trajectory_id: Sha256Digest
    acquisition_absolute_cfo_hz: float
    residual_half_width_hz: Annotated[float, Field(gt=0)] = 2_000.0
    qin_symbol_indices: Literal["zero-based-odd-1-through-299"] = "zero-based-odd-1-through-299"

    @model_validator(mode="after")
    def _center_is_finite(self) -> Self:
        if not math.isfinite(self.acquisition_absolute_cfo_hz):
            raise ValueError("acquisition trajectory center must be finite")
        return self


class OddQinResponseRequestV1(_ResearchModel):
    prediction_ledger_digest: Sha256Digest
    authority: OddQinTargetAuthorityV1


class OddQinResponseMeasurementV1(_ResearchModel):
    prediction_ledger_digest: Sha256Digest
    target: ForecastTargetKeyV1
    status: ResponseStatus
    missing_reason: ReasonCode | None = None
    support_reasons: tuple[ReasonCode, ...] = ()
    accuracy_disposition: AccuracyDisposition
    odd_absolute_cfo_hz: float | None = None
    odd_frequency_uncertainty_hz: float | None = None
    odd_exact_coherence: float | None = None
    odd_rolled_control_coherence: float | None = None
    odd_coherence_margin: float | None = None
    odd_phase_residual_rms_rad: float | None = None
    odd_search_boundary: bool | None = None

    @model_validator(mode="after")
    def _response_is_closed(self) -> Self:
        values = (
            self.odd_absolute_cfo_hz,
            self.odd_frequency_uncertainty_hz,
            self.odd_exact_coherence,
            self.odd_rolled_control_coherence,
            self.odd_coherence_margin,
            self.odd_phase_residual_rms_rad,
        )
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("odd-Qin response value must be finite")
        has_measurement = all(value is not None for value in values)
        has_any_measurement = any(value is not None for value in values)
        if self.status in {"finite", "boundary"}:
            if (
                self.missing_reason is not None
                or self.support_reasons
                or not has_measurement
                or self.odd_search_boundary is None
            ):
                raise ValueError("finite odd-Qin response requires all specificity fields")
            expected_boundary = self.status == "boundary"
            expected_disposition: AccuracyDisposition = (
                "excluded_boundary" if expected_boundary else "eligible"
            )
            if self.odd_search_boundary is not expected_boundary:
                raise ValueError("odd-Qin boundary status and search flag disagree")
            if self.accuracy_disposition != expected_disposition:
                raise ValueError("odd-Qin finite accuracy disposition disagrees")
            if self.odd_frequency_uncertainty_hz is not None and (
                self.odd_frequency_uncertainty_hz <= 0
            ):
                raise ValueError("odd-Qin frequency uncertainty must be positive")
            exact = self.odd_exact_coherence
            control = self.odd_rolled_control_coherence
            margin = self.odd_coherence_margin
            if exact is None or control is None or margin is None:
                raise ValueError("finite odd-Qin response lacks specificity evidence")
            coherences = (exact, control)
            if any(value is not None and not 0 <= value <= 1 for value in coherences):
                raise ValueError("odd-Qin coherences must lie in [0, 1]")
            if not math.isclose(
                margin,
                exact - control,
                abs_tol=1e-12,
            ):
                raise ValueError("odd-Qin coherence margin disagrees with exact minus control")
            if self.odd_phase_residual_rms_rad is not None and (
                self.odd_phase_residual_rms_rad < 0
            ):
                raise ValueError("odd-Qin phase residual RMS must be non-negative")
        elif self.status == "no_support":
            if (
                self.missing_reason is not None
                or not self.support_reasons
                or has_any_measurement
                or self.odd_search_boundary is not None
                or self.accuracy_disposition != "excluded_no_support"
            ):
                raise ValueError("no-support odd-Qin response requires reasons and no values")
        elif (
            self.missing_reason is None
            or self.support_reasons
            or has_any_measurement
            or self.odd_search_boundary is not None
            or self.accuracy_disposition != "missing"
        ):
            raise ValueError("missing odd-Qin response requires one reason and no values")
        return self


class OddQinResponsePort(Protocol):
    """Port implemented later by a digest-pinned odd-symbol-only adapter."""

    def measure_odd_qin(self, request: OddQinResponseRequestV1) -> OddQinResponseMeasurementV1:
        """Measure exactly the odd Qin fold named by ``request``."""


class OddQinAttachmentRowV1(_ResearchModel):
    target: ForecastTargetKeyV1
    prediction_ledger_digest: Sha256Digest
    membership_mutated: Literal[False] = False
    response_denominator_member: Literal[True] = True
    response: OddQinResponseMeasurementV1

    @model_validator(mode="after")
    def _row_matches_response(self) -> Self:
        if self.response.target != self.target:
            raise ValueError("attached response target disagrees")
        if self.response.prediction_ledger_digest != self.prediction_ledger_digest:
            raise ValueError("attached response prediction digest disagrees")
        return self


class OddQinAttachmentLedgerV1(_ResearchModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.doppler-holdout-odd-attachment/v1"
    ]
    prediction_ledger_digest: Sha256Digest
    prediction_membership_or_values_mutated: Literal[False]
    target_count: Annotated[int, Field(gt=0)]
    finite_response_count: Annotated[int, Field(ge=0)]
    accuracy_eligible_count: Annotated[int, Field(ge=0)]
    boundary_response_count: Annotated[int, Field(ge=0)]
    no_support_response_count: Annotated[int, Field(ge=0)]
    missing_response_count: Annotated[int, Field(ge=0)]
    rows: tuple[OddQinAttachmentRowV1, ...]
    attachment_digest: Sha256Digest

    @model_validator(mode="after")
    def _attachment_is_closed(self) -> Self:
        identities = tuple(row.target.identity() for row in self.rows)
        if len(self.rows) != self.target_count or len(set(identities)) != len(identities):
            raise ValueError("odd attachment target accounting is not closed")
        statuses = tuple(row.response.status for row in self.rows)
        finite = sum(status in {"finite", "boundary"} for status in statuses)
        expected_counts = (
            finite,
            sum(row.response.accuracy_disposition == "eligible" for row in self.rows),
            statuses.count("boundary"),
            statuses.count("no_support"),
            statuses.count("missing"),
        )
        actual_counts = (
            self.finite_response_count,
            self.accuracy_eligible_count,
            self.boundary_response_count,
            self.no_support_response_count,
            self.missing_response_count,
        )
        if actual_counts != expected_counts or sum(actual_counts[2:]) + actual_counts[1] != (
            self.target_count
        ):
            raise ValueError("odd attachment response accounting disagrees")
        if any(row.prediction_ledger_digest != self.prediction_ledger_digest for row in self.rows):
            raise ValueError("odd attachment row uses another prediction ledger")
        content = self.model_dump(mode="json", exclude={"attachment_digest"})
        if self.attachment_digest != canonical_digest(content):
            raise ValueError("odd attachment digest disagrees")
        return self


def acquisition_trajectory_center_hz(
    episode: DerivedHoldoutEpisodeV1,
    *,
    target_reference_sample: float,
    sample_rate_hz: int,
) -> float:
    """Evaluate the inherited source-bound trajectory without target-even CFO."""

    if sample_rate_hz <= 0 or not math.isfinite(target_reference_sample):
        raise ValueError("target trajectory coordinate is invalid")
    trajectory = episode.alias_trajectory
    source = episode.source
    source_bound_cfo_hz = (
        source.tracking_cfo_hz
        + (trajectory.final_alias_index - source.observed_alias_index) * SYMBOL_ALIAS_SPACING_HZ
    )
    model_at_source = float(
        np.polyval(
            trajectory.absolute_coefficients_hz,
            source.detection_time_s - trajectory.reference_time_s,
        )
    )
    target_time_s = target_reference_sample / sample_rate_hz
    center = (
        source_bound_cfo_hz
        + float(
            np.polyval(
                trajectory.absolute_coefficients_hz,
                target_time_s - trajectory.reference_time_s,
            )
        )
        - model_at_source
    )
    if not math.isfinite(center):
        raise ValueError("acquisition trajectory center is not finite")
    return center


def build_odd_qin_target_authorities(
    manifest: DopplerHoldoutDerivedManifestV2,
    prediction_ledger: DopplerHoldoutPredictionLedgerV1,
    *,
    residual_half_width_hz: float = 2_000.0,
) -> tuple[OddQinTargetAuthorityV1, ...]:
    """Bind each frozen prediction key to its inherited trajectory center."""

    capture_by_id = {capture.session_id: capture for capture in manifest.captures}
    output: list[OddQinTargetAuthorityV1] = []
    for row in prediction_ledger.rows:
        capture = capture_by_id.get(row.target.session_id)
        if capture is None or capture.status != "evaluable":
            raise ValueError("prediction target is absent from the evaluable v2 cohort")
        episode = capture.inherited_v1_disposition.episode
        if episode is None or episode.episode_id != row.target.episode_id:
            raise ValueError("prediction target episode authority disagrees")
        output.append(
            OddQinTargetAuthorityV1(
                target=row.target,
                scope_key=episode.scope_key,
                stream_id=episode.stream_id,
                radio_id=episode.radio_id,
                receiver_id=episode.receiver_id,
                edge=episode.edge,
                source_id=episode.source.source_id,
                branch_id=episode.alias_trajectory.branch_id,
                trajectory_id=episode.alias_trajectory.trajectory_id,
                acquisition_absolute_cfo_hz=acquisition_trajectory_center_hz(
                    episode,
                    target_reference_sample=row.target.reference_sample,
                    sample_rate_hz=capture.sample_rate_hz,
                ),
                residual_half_width_hz=residual_half_width_hz,
            )
        )
    return tuple(output)


def attach_odd_qin_responses(
    prediction_ledger: DopplerHoldoutPredictionLedgerV1,
    authorities: Sequence[OddQinTargetAuthorityV1],
    port: OddQinResponsePort,
) -> OddQinAttachmentLedgerV1:
    """Attach one response per immutable target without changing predictions."""

    authority_by_key = {authority.target.identity(): authority for authority in authorities}
    expected = tuple(row.target.identity() for row in prediction_ledger.rows)
    if len(authority_by_key) != len(authorities) or set(authority_by_key) != set(expected):
        raise ValueError("odd-Qin authority inventory must exactly match prediction targets")
    rows: list[OddQinAttachmentRowV1] = []
    for prediction in prediction_ledger.rows:
        request = OddQinResponseRequestV1(
            prediction_ledger_digest=prediction_ledger.ledger_digest,
            authority=authority_by_key[prediction.target.identity()],
        )
        response = port.measure_odd_qin(request)
        if response.target != prediction.target:
            raise ValueError("odd-Qin port returned another target")
        if response.prediction_ledger_digest != prediction_ledger.ledger_digest:
            raise ValueError("odd-Qin port returned another prediction digest")
        rows.append(
            OddQinAttachmentRowV1(
                target=prediction.target,
                prediction_ledger_digest=prediction_ledger.ledger_digest,
                response=response,
            )
        )
    document = {
        "schema": ODD_ATTACHMENT_SCHEMA,
        "prediction_ledger_digest": prediction_ledger.ledger_digest,
        "prediction_membership_or_values_mutated": False,
        "target_count": len(rows),
        "finite_response_count": sum(row.response.status in {"finite", "boundary"} for row in rows),
        "accuracy_eligible_count": sum(
            row.response.accuracy_disposition == "eligible" for row in rows
        ),
        "boundary_response_count": sum(row.response.status == "boundary" for row in rows),
        "no_support_response_count": sum(row.response.status == "no_support" for row in rows),
        "missing_response_count": sum(row.response.status == "missing" for row in rows),
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    return OddQinAttachmentLedgerV1.model_validate(
        {**document, "attachment_digest": canonical_digest(document)}
    )
