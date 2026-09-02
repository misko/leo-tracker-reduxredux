"""Additive GLRT frame-epoch tracking contract for Standard-native paths."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV2
from leo.contracts.standard_pipeline import BoundedText
from leo.contracts.states import StarlinkEdge


class NativeGlrtEpochLockletStatusV1(StrEnum):
    COMPLETE = "complete"
    INSUFFICIENT = "insufficient"


class NativeGlrtEpochObservationV1(ContractModel):
    """One GLRT window epoch and its disclosed fit membership."""

    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    global_center_time_s: Annotated[float, Field(ge=0)]
    global_epoch_device_sample: Annotated[int, Field(ge=0)]
    raw_cfo_hz: float
    hough_alias_index: int
    canonical_cfo_hz: float
    frame_phase_s: Annotated[float, Field(ge=0, lt=1.0 / 750.0)]
    unwrapped_frame_phase_s: float
    cfo_branch_inlier: bool
    epoch_fit_inlier: bool
    linear_residual_s: float | None
    quadratic_residual_s: float | None

    @field_validator(
        "global_center_time_s",
        "raw_cfo_hz",
        "canonical_cfo_hz",
        "frame_phase_s",
        "unwrapped_frame_phase_s",
        "linear_residual_s",
        "quadratic_residual_s",
    )
    @classmethod
    def _value_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("GLRT epoch observation values must be finite")
        return value

    @model_validator(mode="after")
    def _membership_is_closed(self) -> Self:
        if self.epoch_fit_inlier and not self.cfo_branch_inlier:
            raise ValueError("GLRT epoch inlier escaped its CFO-selected branch")
        residuals_present = (
            self.linear_residual_s is not None and self.quadratic_residual_s is not None
        )
        if residuals_present != self.epoch_fit_inlier:
            raise ValueError("GLRT epoch residuals do not close fit membership")
        return self


class NativeGlrtEpochPolynomialFitV1(ContractModel):
    """One timing polynomial expressed at a numerically stable reference time."""

    schema_version: Literal[1] = 1
    polynomial_degree: Literal[1, 2]
    timing_model: Literal["phase=p0+drift*dt+0.5*curvature*dt^2"] = (
        "phase=p0+drift*dt+0.5*curvature*dt^2"
    )
    point_count: Annotated[int, Field(ge=3)]
    reference_time_s: Annotated[float, Field(ge=0)]
    phase_at_reference_s: float
    timing_drift_s_s: float
    formal_timing_drift_sigma_s_s: Annotated[float, Field(ge=0)]
    timing_curvature_s_s2: float
    formal_timing_curvature_sigma_s_s2: Annotated[float, Field(ge=0)]
    equivalent_doppler_at_reference_hz: float
    formal_equivalent_doppler_sigma_hz: Annotated[float, Field(ge=0)]
    equivalent_doppler_rate_hz_s: float
    formal_equivalent_doppler_rate_sigma_hz_s: Annotated[float, Field(ge=0)]
    residual_rms_s: Annotated[float, Field(ge=0)]
    residual_mad_scale_s: Annotated[float, Field(ge=0)]
    maximum_absolute_residual_s: Annotated[float, Field(ge=0)]
    fit_digest: Sha256Digest

    @field_validator(
        "reference_time_s",
        "phase_at_reference_s",
        "timing_drift_s_s",
        "formal_timing_drift_sigma_s_s",
        "timing_curvature_s_s2",
        "formal_timing_curvature_sigma_s_s2",
        "equivalent_doppler_at_reference_hz",
        "formal_equivalent_doppler_sigma_hz",
        "equivalent_doppler_rate_hz_s",
        "formal_equivalent_doppler_rate_sigma_hz_s",
        "residual_rms_s",
        "residual_mad_scale_s",
        "maximum_absolute_residual_s",
    )
    @classmethod
    def _value_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("GLRT epoch fit values must be finite")
        return value

    @model_validator(mode="after")
    def _fit_is_closed(self) -> Self:
        if self.polynomial_degree == 1 and (
            self.timing_curvature_s_s2 != 0.0 or self.equivalent_doppler_rate_hz_s != 0.0
        ):
            raise ValueError("linear GLRT epoch fit carries curvature")
        if self.polynomial_degree == 1 and (
            self.formal_timing_curvature_sigma_s_s2 != 0.0
            or self.formal_equivalent_doppler_rate_sigma_hz_s != 0.0
        ):
            raise ValueError("linear GLRT epoch fit carries curvature uncertainty")
        if self.fit_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"fit_digest"})
        ):
            raise ValueError("GLRT epoch fit digest does not match")
        return self


class NativeGlrtEpochCfoSelectionV1(ContractModel):
    """CFO-only dominant-branch selection, independent of epoch values."""

    schema_version: Literal[1] = 1
    candidate_count: Annotated[int, Field(ge=0)]
    selected_count: Annotated[int, Field(ge=0)]
    reference_time_s: Annotated[float, Field(ge=0)] | None
    quadratic_coefficients_hz: tuple[float, float, float] | None
    robust_scale_hz: Annotated[float, Field(ge=0)] | None
    selection_digest: Sha256Digest

    @field_validator("reference_time_s", "robust_scale_hz")
    @classmethod
    def _optional_value_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("GLRT CFO-selection values must be finite")
        return value

    @field_validator("quadratic_coefficients_hz")
    @classmethod
    def _coefficients_are_finite(
        cls, value: tuple[float, float, float] | None
    ) -> tuple[float, float, float] | None:
        if value is not None and any(not math.isfinite(item) for item in value):
            raise ValueError("GLRT CFO-selection coefficients must be finite")
        return value

    @model_validator(mode="after")
    def _selection_is_closed(self) -> Self:
        if self.selected_count > self.candidate_count:
            raise ValueError("GLRT CFO-selected count exceeds candidates")
        fields_present = (
            self.reference_time_s is not None
            and self.quadratic_coefficients_hz is not None
            and self.robust_scale_hz is not None
        )
        if fields_present != bool(self.selected_count):
            raise ValueError("GLRT CFO-selection fit fields do not close")
        if self.selection_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"selection_digest"})
        ):
            raise ValueError("GLRT CFO-selection digest does not match")
        return self


class NativeGlrtEpochLockletV1(ContractModel):
    """One gap-bounded, continuity-local epoch fit."""

    schema_version: Literal[1] = 1
    continuity_segment_index: Annotated[int, Field(ge=0)]
    locklet_index: Annotated[int, Field(ge=0)]
    source_hough_track_label: BoundedText
    global_start_time_s: Annotated[float, Field(ge=0)]
    global_end_time_s: Annotated[float, Field(ge=0)]
    status: NativeGlrtEpochLockletStatusV1
    reason: BoundedText
    cfo_selection: NativeGlrtEpochCfoSelectionV1
    epoch_inlier_count: Annotated[int, Field(ge=0)]
    observations: tuple[NativeGlrtEpochObservationV1, ...]
    linear_fit: NativeGlrtEpochPolynomialFitV1 | None
    quadratic_fit: NativeGlrtEpochPolynomialFitV1 | None
    locklet_digest: Sha256Digest

    @model_validator(mode="after")
    def _locklet_is_closed(self) -> Self:
        if not self.observations:
            raise ValueError("GLRT epoch locklet has no observations")
        if self.global_end_time_s < self.global_start_time_s:
            raise ValueError("GLRT epoch locklet time support regressed")
        indexes = tuple(item.opportunity_index for item in self.observations)
        if indexes != tuple(sorted(set(indexes))):
            raise ValueError("GLRT epoch observations are not canonical")
        if self.cfo_selection.candidate_count != len(self.observations):
            raise ValueError("GLRT epoch candidate accounting does not close")
        if self.cfo_selection.selected_count != sum(
            item.cfo_branch_inlier for item in self.observations
        ):
            raise ValueError("GLRT epoch CFO membership does not close")
        if self.epoch_inlier_count != sum(item.epoch_fit_inlier for item in self.observations):
            raise ValueError("GLRT epoch fit membership does not close")
        times = tuple(item.global_center_time_s for item in self.observations)
        if (
            times != tuple(sorted(times))
            or self.global_start_time_s != times[0]
            or self.global_end_time_s != times[-1]
        ):
            raise ValueError("GLRT epoch locklet time support does not close")
        complete = self.status is NativeGlrtEpochLockletStatusV1.COMPLETE
        if complete != (self.linear_fit is not None and self.quadratic_fit is not None):
            raise ValueError("GLRT epoch fit availability disagrees with status")
        if complete and (
            self.linear_fit is None
            or self.quadratic_fit is None
            or self.linear_fit.polynomial_degree != 1
            or self.quadratic_fit.polynomial_degree != 2
            or self.linear_fit.point_count != self.epoch_inlier_count
            or self.quadratic_fit.point_count != self.epoch_inlier_count
            or self.linear_fit.reference_time_s != self.quadratic_fit.reference_time_s
        ):
            raise ValueError("GLRT epoch polynomial fits do not share exact support")
        if complete:
            assert self.linear_fit is not None and self.quadratic_fit is not None
            for observation in self.observations:
                if not observation.epoch_fit_inlier:
                    continue
                linear_dt = observation.global_center_time_s - self.linear_fit.reference_time_s
                quadratic_dt = (
                    observation.global_center_time_s - self.quadratic_fit.reference_time_s
                )
                linear_prediction = (
                    self.linear_fit.phase_at_reference_s
                    + self.linear_fit.timing_drift_s_s * linear_dt
                )
                quadratic_prediction = (
                    self.quadratic_fit.phase_at_reference_s
                    + self.quadratic_fit.timing_drift_s_s * quadratic_dt
                    + 0.5 * self.quadratic_fit.timing_curvature_s_s2 * quadratic_dt**2
                )
                expected_linear = _frame_phase_residual(
                    observation.frame_phase_s, linear_prediction
                )
                expected_quadratic = _frame_phase_residual(
                    observation.frame_phase_s, quadratic_prediction
                )
                if not (
                    math.isclose(
                        observation.linear_residual_s or 0.0,
                        expected_linear,
                        abs_tol=1e-12,
                    )
                    and math.isclose(
                        observation.quadratic_residual_s or 0.0,
                        expected_quadratic,
                        abs_tol=1e-12,
                    )
                ):
                    raise ValueError("GLRT epoch observation residuals do not close their fits")
        if self.locklet_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"locklet_digest"})
        ):
            raise ValueError("GLRT epoch locklet digest does not match")
        return self


class StandardNativeGlrtEpochTrackingV1(ContractModel):
    """Receiver-relative epoch fits derived from one immutable GLRT product."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-native-glrt-epoch-tracking-v1"] = (
        "standard-native-glrt-epoch-tracking-v1"
    )
    source: StandardNativeSourceV2
    source_glrt_product_digest: Sha256Digest
    source_glrt_result_digest: Sha256Digest
    configuration_digest: Sha256Digest
    frame_rate_hz: Literal[750] = 750
    starlink_edge: StarlinkEdge
    rf_reference_hz: Annotated[float, Field(gt=0)]
    rf_reference_provenance: Literal["documented_lnb_lo_plus_tuned_if_center"] = (
        "documented_lnb_lo_plus_tuned_if_center"
    )
    equivalent_doppler_sign_convention: Literal[
        "equivalent_doppler_hz=-rf_reference_hz*d(frame_arrival_phase_s)/dt"
    ] = "equivalent_doppler_hz=-rf_reference_hz*d(frame_arrival_phase_s)/dt"
    cfo_alias_spacing_hz: Annotated[float, Field(gt=0)]
    cfo_canonicalization: Literal["canonical_cfo=raw_cfo-alias_index*alias_spacing"] = (
        "canonical_cfo=raw_cfo-alias_index*alias_spacing"
    )
    receiver_relative: Literal[True] = True
    cfo_selection_uses_epoch: Literal[False] = False
    cross_continuity_fit_permitted: Literal[False] = False
    locklets: tuple[NativeGlrtEpochLockletV1, ...]
    limitations: tuple[BoundedText, ...]
    result_digest: Sha256Digest

    @field_validator("rf_reference_hz", "cfo_alias_spacing_hz")
    @classmethod
    def _rf_reference_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("GLRT epoch frequency references must be finite")
        return value

    @model_validator(mode="after")
    def _result_is_closed(self) -> Self:
        ordering = tuple(
            (item.continuity_segment_index, item.locklet_index, item.global_start_time_s)
            for item in self.locklets
        )
        if ordering != tuple(sorted(ordering)):
            raise ValueError("GLRT epoch locklets are not canonical")
        segments = {item.segment_index: item for item in self.source.continuity_segments}
        segment_indexes = set(segments)
        if any(item.continuity_segment_index not in segment_indexes for item in self.locklets):
            raise ValueError("GLRT epoch locklet escaped source continuity")
        if not math.isclose(self.cfo_alias_spacing_hz, 2_500_000 / 11, abs_tol=1e-12):
            raise ValueError("GLRT epoch CFO alias spacing differs from its source algorithm")
        if not self.limitations:
            raise ValueError("GLRT epoch result must disclose limitations")
        for locklet in self.locklets:
            segment = segments[locklet.continuity_segment_index]
            start_s = segment.device_sample_start / self.source.sample_rate_hz
            stop_s = segment.device_sample_stop / self.source.sample_rate_hz
            if locklet.global_start_time_s < start_s or locklet.global_end_time_s > stop_s:
                raise ValueError("GLRT epoch locklet escaped its continuity time span")
            for observation in locklet.observations:
                if not (
                    segment.device_sample_start
                    <= observation.global_epoch_device_sample
                    < segment.device_sample_stop
                ):
                    raise ValueError("GLRT epoch observation escaped its continuity samples")
                expected_phase = (
                    (observation.global_epoch_device_sample * self.frame_rate_hz)
                    % self.source.sample_rate_hz
                ) / (self.source.sample_rate_hz * self.frame_rate_hz)
                if not math.isclose(observation.frame_phase_s, expected_phase, abs_tol=1e-15):
                    raise ValueError("GLRT epoch frame phase does not close its device sample")
                if not math.isclose(
                    observation.canonical_cfo_hz,
                    observation.raw_cfo_hz
                    - observation.hough_alias_index * self.cfo_alias_spacing_hz,
                    abs_tol=1e-9,
                ):
                    raise ValueError("GLRT epoch canonical CFO does not close its alias index")
                if not math.isclose(
                    _frame_phase_residual(
                        observation.unwrapped_frame_phase_s,
                        observation.frame_phase_s,
                    ),
                    0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("GLRT epoch unwrapped phase changed its frame phase")
            for fit in (locklet.linear_fit, locklet.quadratic_fit):
                if fit is None:
                    continue
                if not (
                    math.isclose(
                        fit.equivalent_doppler_at_reference_hz,
                        -self.rf_reference_hz * fit.timing_drift_s_s,
                        rel_tol=1e-12,
                        abs_tol=1e-6,
                    )
                    and math.isclose(
                        fit.equivalent_doppler_rate_hz_s,
                        -self.rf_reference_hz * fit.timing_curvature_s_s2,
                        rel_tol=1e-12,
                        abs_tol=1e-6,
                    )
                ):
                    raise ValueError("GLRT epoch equivalent Doppler does not close timing fit")
        if self.result_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("GLRT epoch result digest does not match")
        return self


class NativeGlrtFractionalEpochObservationV2(ContractModel):
    """One GLRT epoch measured from a bracketed fractional score peak."""

    schema_version: Literal[2] = 2
    opportunity_index: Annotated[int, Field(ge=0)]
    global_center_time_s: Annotated[float, Field(ge=0)]
    integer_global_epoch_device_sample: Annotated[int, Field(ge=0)]
    fractional_epoch_offset_samples: Annotated[float, Field(ge=-1.5, le=1.5)]
    fractional_global_epoch_device_sample: Annotated[float, Field(ge=0)]
    raw_cfo_hz: float
    hough_alias_index: int
    canonical_cfo_hz: float
    frame_phase_s: Annotated[float, Field(ge=0, lt=1.0 / 750.0)]
    unwrapped_frame_phase_s: float
    cfo_branch_inlier: bool
    epoch_fit_inlier: bool
    linear_residual_s: float | None
    quadratic_residual_s: float | None

    @field_validator(
        "global_center_time_s",
        "fractional_epoch_offset_samples",
        "fractional_global_epoch_device_sample",
        "raw_cfo_hz",
        "canonical_cfo_hz",
        "frame_phase_s",
        "unwrapped_frame_phase_s",
        "linear_residual_s",
        "quadratic_residual_s",
    )
    @classmethod
    def _value_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("fractional GLRT epoch observation values must be finite")
        return value

    @model_validator(mode="after")
    def _membership_is_closed(self) -> Self:
        if not math.isclose(
            self.fractional_global_epoch_device_sample,
            self.integer_global_epoch_device_sample + self.fractional_epoch_offset_samples,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("fractional GLRT epoch sample does not close its integer origin")
        if self.epoch_fit_inlier and not self.cfo_branch_inlier:
            raise ValueError("fractional GLRT epoch inlier escaped its CFO-selected branch")
        residuals_present = (
            self.linear_residual_s is not None and self.quadratic_residual_s is not None
        )
        if residuals_present != self.epoch_fit_inlier:
            raise ValueError("fractional GLRT epoch residuals do not close fit membership")
        return self


class NativeGlrtFractionalEpochLockletV2(ContractModel):
    """One gap-bounded locklet fitted from local fractional measurements."""

    schema_version: Literal[2] = 2
    continuity_segment_index: Annotated[int, Field(ge=0)]
    locklet_index: Annotated[int, Field(ge=0)]
    source_hough_track_label: BoundedText
    global_start_time_s: Annotated[float, Field(ge=0)]
    global_end_time_s: Annotated[float, Field(ge=0)]
    status: NativeGlrtEpochLockletStatusV1
    reason: BoundedText
    cfo_selection: NativeGlrtEpochCfoSelectionV1
    epoch_inlier_count: Annotated[int, Field(ge=0)]
    observations: tuple[NativeGlrtFractionalEpochObservationV2, ...]
    linear_fit: NativeGlrtEpochPolynomialFitV1 | None
    quadratic_fit: NativeGlrtEpochPolynomialFitV1 | None
    locklet_digest: Sha256Digest

    @model_validator(mode="after")
    def _locklet_is_closed(self) -> Self:
        if not self.observations or self.global_end_time_s < self.global_start_time_s:
            raise ValueError("fractional GLRT epoch locklet support is invalid")
        indexes = tuple(item.opportunity_index for item in self.observations)
        times = tuple(item.global_center_time_s for item in self.observations)
        if indexes != tuple(sorted(set(indexes))) or times != tuple(sorted(times)):
            raise ValueError("fractional GLRT epoch observations are not canonical")
        if self.global_start_time_s != times[0] or self.global_end_time_s != times[-1]:
            raise ValueError("fractional GLRT epoch locklet time support does not close")
        if self.cfo_selection.candidate_count != len(self.observations):
            raise ValueError("fractional GLRT epoch candidate accounting does not close")
        if self.cfo_selection.selected_count != sum(
            item.cfo_branch_inlier for item in self.observations
        ) or self.epoch_inlier_count != sum(item.epoch_fit_inlier for item in self.observations):
            raise ValueError("fractional GLRT epoch fit membership does not close")
        complete = self.status is NativeGlrtEpochLockletStatusV1.COMPLETE
        if complete != (self.linear_fit is not None and self.quadratic_fit is not None):
            raise ValueError("fractional GLRT epoch fit availability disagrees with status")
        if complete:
            assert self.linear_fit is not None and self.quadratic_fit is not None
            if (
                self.linear_fit.polynomial_degree != 1
                or self.quadratic_fit.polynomial_degree != 2
                or self.linear_fit.point_count != self.epoch_inlier_count
                or self.quadratic_fit.point_count != self.epoch_inlier_count
                or self.linear_fit.reference_time_s != self.quadratic_fit.reference_time_s
            ):
                raise ValueError("fractional GLRT polynomial fits do not share exact support")
            for observation in self.observations:
                if not observation.epoch_fit_inlier:
                    continue
                linear_dt = observation.global_center_time_s - self.linear_fit.reference_time_s
                quadratic_dt = (
                    observation.global_center_time_s - self.quadratic_fit.reference_time_s
                )
                linear_prediction = (
                    self.linear_fit.phase_at_reference_s
                    + self.linear_fit.timing_drift_s_s * linear_dt
                )
                quadratic_prediction = (
                    self.quadratic_fit.phase_at_reference_s
                    + self.quadratic_fit.timing_drift_s_s * quadratic_dt
                    + 0.5 * self.quadratic_fit.timing_curvature_s_s2 * quadratic_dt**2
                )
                if not (
                    math.isclose(
                        observation.linear_residual_s or 0.0,
                        _frame_phase_residual(observation.frame_phase_s, linear_prediction),
                        abs_tol=1e-12,
                    )
                    and math.isclose(
                        observation.quadratic_residual_s or 0.0,
                        _frame_phase_residual(observation.frame_phase_s, quadratic_prediction),
                        abs_tol=1e-12,
                    )
                ):
                    raise ValueError("fractional GLRT residuals do not close their fits")
        if self.locklet_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"locklet_digest"})
        ):
            raise ValueError("fractional GLRT epoch locklet digest does not match")
        return self


class StandardNativeGlrtEpochTrackingV2(ContractModel):
    """Receiver-relative fits using independently measured fractional GLRT peaks."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-native-glrt-epoch-tracking-v2"] = (
        "standard-native-glrt-epoch-tracking-v2"
    )
    source: StandardNativeSourceV2
    source_glrt_product_digest: Sha256Digest
    source_glrt_result_digest: Sha256Digest
    source_fractional_epoch_product_digest: Sha256Digest
    source_fractional_epoch_result_digest: Sha256Digest
    configuration_digest: Sha256Digest
    frame_rate_hz: Literal[750] = 750
    starlink_edge: StarlinkEdge
    fractional_epoch_method: Literal["three-cell-log-parabola-v1"] = "three-cell-log-parabola-v1"
    rf_reference_hz: Annotated[float, Field(gt=0)]
    rf_reference_provenance: Literal["documented_lnb_lo_plus_tuned_if_center"] = (
        "documented_lnb_lo_plus_tuned_if_center"
    )
    equivalent_doppler_sign_convention: Literal[
        "equivalent_doppler_hz=-rf_reference_hz*d(frame_arrival_phase_s)/dt"
    ] = "equivalent_doppler_hz=-rf_reference_hz*d(frame_arrival_phase_s)/dt"
    cfo_alias_spacing_hz: Annotated[float, Field(gt=0)]
    cfo_canonicalization: Literal["canonical_cfo=raw_cfo-alias_index*alias_spacing"] = (
        "canonical_cfo=raw_cfo-alias_index*alias_spacing"
    )
    receiver_relative: Literal[True] = True
    cfo_selection_uses_epoch: Literal[False] = False
    cross_continuity_fit_permitted: Literal[False] = False
    locklets: tuple[NativeGlrtFractionalEpochLockletV2, ...]
    limitations: tuple[BoundedText, ...]
    result_digest: Sha256Digest

    @field_validator("rf_reference_hz", "cfo_alias_spacing_hz")
    @classmethod
    def _frequency_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("fractional GLRT epoch frequency references must be finite")
        return value

    @model_validator(mode="after")
    def _result_is_closed(self) -> Self:
        ordering = tuple(
            (item.continuity_segment_index, item.locklet_index, item.global_start_time_s)
            for item in self.locklets
        )
        if ordering != tuple(sorted(ordering)):
            raise ValueError("fractional GLRT epoch locklets are not canonical")
        segments = {item.segment_index: item for item in self.source.continuity_segments}
        if any(item.continuity_segment_index not in segments for item in self.locklets):
            raise ValueError("fractional GLRT epoch locklet escaped source continuity")
        if not math.isclose(self.cfo_alias_spacing_hz, 2_500_000 / 11, abs_tol=1e-12):
            raise ValueError("fractional GLRT CFO alias spacing differs from its source algorithm")
        if not self.limitations:
            raise ValueError("fractional GLRT epoch result must disclose limitations")
        period_s = 1.0 / self.frame_rate_hz
        for locklet in self.locklets:
            segment = segments[locklet.continuity_segment_index]
            start_s = segment.device_sample_start / self.source.sample_rate_hz
            stop_s = segment.device_sample_stop / self.source.sample_rate_hz
            if locklet.global_start_time_s < start_s or locklet.global_end_time_s > stop_s:
                raise ValueError("fractional GLRT locklet escaped its continuity time span")
            for observation in locklet.observations:
                if not (
                    segment.device_sample_start
                    <= observation.fractional_global_epoch_device_sample
                    < segment.device_sample_stop
                ):
                    raise ValueError("fractional GLRT observation escaped continuity samples")
                integer_phase = (
                    (observation.integer_global_epoch_device_sample * self.frame_rate_hz)
                    % self.source.sample_rate_hz
                ) / (self.source.sample_rate_hz * self.frame_rate_hz)
                expected_phase = (
                    integer_phase
                    + observation.fractional_epoch_offset_samples / self.source.sample_rate_hz
                ) % period_s
                if not math.isclose(observation.frame_phase_s, expected_phase, abs_tol=1e-15):
                    raise ValueError("fractional GLRT frame phase does not close its peak")
                if not math.isclose(
                    observation.canonical_cfo_hz,
                    observation.raw_cfo_hz
                    - observation.hough_alias_index * self.cfo_alias_spacing_hz,
                    abs_tol=1e-9,
                ):
                    raise ValueError("fractional GLRT canonical CFO does not close its alias")
                if not math.isclose(
                    _frame_phase_residual(
                        observation.unwrapped_frame_phase_s, observation.frame_phase_s
                    ),
                    0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("fractional GLRT unwrapped phase changed its frame class")
            for fit in (locklet.linear_fit, locklet.quadratic_fit):
                if fit is None:
                    continue
                if not (
                    math.isclose(
                        fit.equivalent_doppler_at_reference_hz,
                        -self.rf_reference_hz * fit.timing_drift_s_s,
                        rel_tol=1e-12,
                        abs_tol=1e-6,
                    )
                    and math.isclose(
                        fit.equivalent_doppler_rate_hz_s,
                        -self.rf_reference_hz * fit.timing_curvature_s_s2,
                        rel_tol=1e-12,
                        abs_tol=1e-6,
                    )
                ):
                    raise ValueError("fractional GLRT equivalent Doppler does not close timing fit")
        if self.result_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("fractional GLRT epoch result digest does not match")
        return self


def _frame_phase_residual(observed_s: float, predicted_s: float) -> float:
    period_s = 1.0 / 750.0
    return (observed_s - predicted_s + period_s / 2.0) % period_s - period_s / 2.0
