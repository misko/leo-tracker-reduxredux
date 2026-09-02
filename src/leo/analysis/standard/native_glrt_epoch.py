"""Continuity-safe frame-epoch tracking derived from native GLRT windows."""

from __future__ import annotations

import io
import math
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native_glrt import StandardNativeFullCaptureGlrt20msV2
from leo.contracts.standard_native_glrt_epoch import (
    NativeGlrtEpochCfoSelectionV1,
    NativeGlrtEpochLockletStatusV1,
    NativeGlrtEpochLockletV1,
    NativeGlrtEpochObservationV1,
    NativeGlrtEpochPolynomialFitV1,
    StandardNativeGlrtEpochTrackingV1,
)
from leo.contracts.starlink_frequency import STARLINK_LNB_LO_HZ

_FRAME_RATE_HZ = 750.0
_FRAME_PERIOD_S = 1.0 / _FRAME_RATE_HZ
_CFO_ALIAS_SPACING_HZ = 2_500_000 / 11
_RENDER_LOCK = Lock()
_COLORS = ("#2563eb", "#ea580c", "#16a34a", "#9333ea", "#0891b2", "#dc2626")


@dataclass(frozen=True, slots=True)
class GlrtEpochTrackingConfig:
    """Frozen robust-fit and support policy for the derived diagnostic."""

    minimum_points: int = 12
    minimum_span_s: float = 0.5
    maximum_candidate_gap_s: float = 2.0
    huber_tuning: float = 1.345
    outlier_scale: float = 4.0
    cfo_scale_floor_hz: float = 25.0
    maximum_quadratic_rms_samples: float = 2.0
    maximum_formal_rate_sigma_hz_s: float = 500.0

    def __post_init__(self) -> None:
        if self.minimum_points < 3:
            raise ValueError("GLRT epoch tracking requires at least three points")
        values = (
            self.minimum_span_s,
            self.maximum_candidate_gap_s,
            self.huber_tuning,
            self.outlier_scale,
            self.cfo_scale_floor_hz,
            self.maximum_quadratic_rms_samples,
            self.maximum_formal_rate_sigma_hz_s,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("GLRT epoch tracking thresholds must be finite and positive")


@dataclass(frozen=True, slots=True)
class _EpochCandidate:
    opportunity_index: int
    global_center_time_s: float
    global_epoch_device_sample: int
    raw_cfo_hz: float
    hough_alias_index: int

    @property
    def canonical_cfo_hz(self) -> float:
        return self.raw_cfo_hz - self.hough_alias_index * _CFO_ALIAS_SPACING_HZ


def glrt_epoch_tracking_configuration_digest(
    config: GlrtEpochTrackingConfig | None = None,
) -> Sha256Digest:
    settings = config or GlrtEpochTrackingConfig()
    return canonical_digest(
        {
            "algorithm_version": "standard-native-glrt-epoch-tracking-v1",
            "configuration": asdict(settings),
            "frame_rate_hz": 750,
            "cfo_alias_spacing_hz": _CFO_ALIAS_SPACING_HZ,
            "equivalent_doppler_sign": "negative_frame_arrival_phase_derivative",
        }
    )


def build_standard_native_glrt_epoch_tracking_v1(
    glrt: StandardNativeFullCaptureGlrt20msV2,
    *,
    source_glrt_product_digest: Sha256Digest,
    config: GlrtEpochTrackingConfig | None = None,
) -> StandardNativeGlrtEpochTrackingV1:
    """Fit receiver-relative GLRT epochs without crossing gaps or resets."""

    settings = config or GlrtEpochTrackingConfig()
    rf_reference_hz = float(STARLINK_LNB_LO_HZ + glrt.source.tuned_center_frequency_hz)
    locklets: list[NativeGlrtEpochLockletV1] = []
    for segment in glrt.segments:
        windows = {item.opportunity_index: item for item in segment.windows}
        segment_locklet_index = 0
        for track in segment.hough.tracks:
            candidates = tuple(
                _EpochCandidate(
                    opportunity_index=window.opportunity_index,
                    global_center_time_s=window.global_center_time_s,
                    global_epoch_device_sample=cast(int, window.global_epoch_device_sample),
                    raw_cfo_hz=observation.raw_cfo_hz,
                    hough_alias_index=observation.alias_index,
                )
                for observation in track.observations
                if (window := windows.get(observation.opportunity_index)) is not None
                and window.global_epoch_device_sample is not None
                and window.tracking_cfo_hz is not None
            )
            for rows in _split_candidate_runs(candidates, settings):
                locklets.append(
                    _fit_locklet(
                        rows,
                        continuity_segment_index=segment.continuity_segment.segment_index,
                        locklet_index=segment_locklet_index,
                        source_hough_track_label=track.track_label,
                        sample_rate_hz=glrt.source.sample_rate_hz,
                        rf_reference_hz=rf_reference_hz,
                        config=settings,
                    )
                )
                segment_locklet_index += 1
    values: dict[str, Any] = {
        "source": glrt.source.model_dump(mode="json"),
        "source_glrt_product_digest": source_glrt_product_digest,
        "source_glrt_result_digest": glrt.result_digest,
        "configuration_digest": glrt_epoch_tracking_configuration_digest(settings),
        "starlink_edge": glrt.starlink_edge.value,
        "rf_reference_hz": rf_reference_hz,
        "cfo_alias_spacing_hz": _CFO_ALIAS_SPACING_HZ,
        "locklets": tuple(item.model_dump(mode="json") for item in locklets),
        "limitations": (
            "Frame epoch is receiver-relative and includes sample-clock and acquisition bias.",
            "CFO Hough membership and robust CFO residuals select branches without epoch timing.",
            "Arrival-time equivalent Doppler uses the physical minus sign; receiver clocks "
            "and acquisition bias can dominate it.",
            "The RF scale is documented LNB LO plus tuned IF center, not a measured carrier RF.",
            "Formal fit sigmas treat overlapping 20 ms windows as independent and are optimistic.",
            "Candidate evidence does not establish Starlink or satellite identity.",
        ),
    }
    digest_values = {
        "schema_version": 1,
        "algorithm_version": "standard-native-glrt-epoch-tracking-v1",
        **values,
        "frame_rate_hz": 750,
        "rf_reference_provenance": "documented_lnb_lo_plus_tuned_if_center",
        "equivalent_doppler_sign_convention": (
            "equivalent_doppler_hz=-rf_reference_hz*d(frame_arrival_phase_s)/dt"
        ),
        "cfo_canonicalization": "canonical_cfo=raw_cfo-alias_index*alias_spacing",
        "receiver_relative": True,
        "cfo_selection_uses_epoch": False,
        "cross_continuity_fit_permitted": False,
    }
    return StandardNativeGlrtEpochTrackingV1.model_validate(
        {**digest_values, "result_digest": canonical_digest(digest_values)}
    )


def _split_candidate_runs(
    rows: tuple[_EpochCandidate, ...],
    config: GlrtEpochTrackingConfig,
) -> tuple[tuple[_EpochCandidate, ...], ...]:
    ordered = tuple(sorted(rows, key=lambda item: item.opportunity_index))
    if not ordered:
        return ()
    runs: list[list[_EpochCandidate]] = [[ordered[0]]]
    for row in ordered[1:]:
        if row.global_center_time_s - runs[-1][-1].global_center_time_s > (
            config.maximum_candidate_gap_s
        ):
            runs.append([row])
        else:
            runs[-1].append(row)
    return tuple(tuple(run) for run in runs)


def _fit_locklet(
    rows: tuple[_EpochCandidate, ...],
    *,
    continuity_segment_index: int,
    locklet_index: int,
    source_hough_track_label: str,
    sample_rate_hz: int,
    rf_reference_hz: float,
    config: GlrtEpochTrackingConfig,
) -> NativeGlrtEpochLockletV1:
    times_s = np.asarray([item.global_center_time_s for item in rows], dtype=np.float64)
    cfo_hz = np.asarray(
        [item.canonical_cfo_hz for item in rows],
        dtype=np.float64,
    )
    phases_s = np.asarray(
        [
            ((item.global_epoch_device_sample * 750) % sample_rate_hz) / (sample_rate_hz * 750)
            for item in rows
        ],
        dtype=np.float64,
    )
    unwrapped_s = phases_s.copy()
    reference_s = float(np.mean(times_s))
    cfo_coefficients: npt.NDArray[np.float64] | None = None
    cfo_scale_hz: float | None = None
    cfo_inliers = np.zeros(len(rows), dtype=bool)
    if len(rows) >= 3 and times_s[-1] > times_s[0]:
        cfo_coefficients, cfo_scale_hz, cfo_inliers = _robust_polynomial_inliers(
            times_s - reference_s,
            cfo_hz,
            degree=2,
            scale_floor=config.cfo_scale_floor_hz,
            config=config,
        )
    selection_values: dict[str, Any] = {
        "candidate_count": len(rows),
        "selected_count": int(np.count_nonzero(cfo_inliers)),
        "reference_time_s": reference_s if cfo_coefficients is not None else None,
        "quadratic_coefficients_hz": (
            None if cfo_coefficients is None else tuple(float(item) for item in cfo_coefficients)
        ),
        "robust_scale_hz": cfo_scale_hz,
    }
    selection = NativeGlrtEpochCfoSelectionV1.model_validate(
        {
            **selection_values,
            "selection_digest": canonical_digest({"schema_version": 1, **selection_values}),
        }
    )

    epoch_inliers = np.zeros(len(rows), dtype=bool)
    linear_fit: NativeGlrtEpochPolynomialFitV1 | None = None
    quadratic_fit: NativeGlrtEpochPolynomialFitV1 | None = None
    linear_residuals = np.full(len(rows), np.nan)
    quadratic_residuals = np.full(len(rows), np.nan)
    selected_indexes = np.flatnonzero(cfo_inliers)
    if selected_indexes.size:
        unwrapped_s[selected_indexes] = np.unwrap(
            phases_s[selected_indexes] / _FRAME_PERIOD_S * 2.0 * np.pi
        ) * (_FRAME_PERIOD_S / (2.0 * np.pi))
    reason = "complete robust epoch fit"
    if len(selected_indexes) < config.minimum_points:
        reason = "too few CFO-selected epoch observations"
    elif times_s[selected_indexes[-1]] - times_s[selected_indexes[0]] < config.minimum_span_s:
        reason = "CFO-selected epoch span is too short"
    else:
        selected_reference_s = float(np.mean(times_s[selected_indexes]))
        _, _, selected_epoch_inliers = _robust_polynomial_inliers(
            times_s[selected_indexes] - selected_reference_s,
            unwrapped_s[selected_indexes],
            degree=2,
            scale_floor=1.0 / sample_rate_hz,
            config=config,
            circular_period_s=_FRAME_PERIOD_S,
        )
        epoch_inliers[selected_indexes[selected_epoch_inliers]] = True
        fit_indexes = np.flatnonzero(epoch_inliers)
        if len(fit_indexes) < config.minimum_points:
            reason = "too few robust epoch observations"
        elif times_s[fit_indexes[-1]] - times_s[fit_indexes[0]] < config.minimum_span_s:
            reason = "robust epoch span is too short"
        else:
            fit_reference_s = float(np.mean(times_s[fit_indexes]))
            linear_coefficients = _least_squares_coefficients(
                times_s[fit_indexes] - fit_reference_s,
                unwrapped_s[fit_indexes],
                degree=1,
            )
            quadratic_coefficients = _least_squares_coefficients(
                times_s[fit_indexes] - fit_reference_s,
                unwrapped_s[fit_indexes],
                degree=2,
            )
            linear_residuals[fit_indexes] = _circular_residual(
                phases_s[fit_indexes],
                _evaluate(linear_coefficients, times_s[fit_indexes] - fit_reference_s),
            )
            quadratic_residuals[fit_indexes] = _circular_residual(
                phases_s[fit_indexes],
                _evaluate(quadratic_coefficients, times_s[fit_indexes] - fit_reference_s),
            )
            linear_fit = _polynomial_contract(
                degree=1,
                coefficients=linear_coefficients,
                reference_time_s=fit_reference_s,
                residuals_s=linear_residuals[fit_indexes],
                local_times_s=times_s[fit_indexes] - fit_reference_s,
                rf_reference_hz=rf_reference_hz,
            )
            quadratic_fit = _polynomial_contract(
                degree=2,
                coefficients=quadratic_coefficients,
                reference_time_s=fit_reference_s,
                residuals_s=quadratic_residuals[fit_indexes],
                local_times_s=times_s[fit_indexes] - fit_reference_s,
                rf_reference_hz=rf_reference_hz,
            )
            if quadratic_fit.residual_rms_s > (
                config.maximum_quadratic_rms_samples / sample_rate_hz
            ):
                reason = "quadratic epoch residual exceeds the sample-aware quality gate"
                linear_fit = None
                quadratic_fit = None
                epoch_inliers[:] = False
            elif (
                quadratic_fit.formal_equivalent_doppler_rate_sigma_hz_s
                > config.maximum_formal_rate_sigma_hz_s
            ):
                reason = "quadratic epoch-rate uncertainty exceeds the quality gate"
                linear_fit = None
                quadratic_fit = None
                epoch_inliers[:] = False

    observations = tuple(
        NativeGlrtEpochObservationV1(
            opportunity_index=item.opportunity_index,
            global_center_time_s=item.global_center_time_s,
            global_epoch_device_sample=item.global_epoch_device_sample,
            raw_cfo_hz=item.raw_cfo_hz,
            hough_alias_index=item.hough_alias_index,
            canonical_cfo_hz=float(cfo_hz[index]),
            frame_phase_s=float(phases_s[index]),
            unwrapped_frame_phase_s=float(unwrapped_s[index]),
            cfo_branch_inlier=bool(cfo_inliers[index]),
            epoch_fit_inlier=bool(epoch_inliers[index] and linear_fit is not None),
            linear_residual_s=(
                float(linear_residuals[index]) if epoch_inliers[index] and linear_fit else None
            ),
            quadratic_residual_s=(
                float(quadratic_residuals[index])
                if epoch_inliers[index] and quadratic_fit
                else None
            ),
        )
        for index, item in enumerate(rows)
    )
    status = (
        NativeGlrtEpochLockletStatusV1.COMPLETE
        if linear_fit is not None and quadratic_fit is not None
        else NativeGlrtEpochLockletStatusV1.INSUFFICIENT
    )
    values = {
        "continuity_segment_index": continuity_segment_index,
        "locklet_index": locklet_index,
        "source_hough_track_label": source_hough_track_label,
        "global_start_time_s": float(times_s[0]),
        "global_end_time_s": float(times_s[-1]),
        "status": status.value,
        "reason": reason,
        "cfo_selection": selection.model_dump(mode="json"),
        "epoch_inlier_count": sum(item.epoch_fit_inlier for item in observations),
        "observations": tuple(item.model_dump(mode="json") for item in observations),
        "linear_fit": None if linear_fit is None else linear_fit.model_dump(mode="json"),
        "quadratic_fit": (None if quadratic_fit is None else quadratic_fit.model_dump(mode="json")),
    }
    return NativeGlrtEpochLockletV1.model_validate(
        {**values, "locklet_digest": canonical_digest({"schema_version": 1, **values})}
    )


def _robust_polynomial_inliers(
    times_s: npt.NDArray[np.float64],
    values: npt.NDArray[np.float64],
    *,
    degree: int,
    scale_floor: float,
    config: GlrtEpochTrackingConfig,
    circular_period_s: float | None = None,
) -> tuple[npt.NDArray[np.float64], float, npt.NDArray[np.bool_]]:
    design = _design(times_s, degree)
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    scale = scale_floor
    for _ in range(50):
        residuals = _residual(values, design @ coefficients, circular_period_s)
        center = float(np.median(residuals))
        scale = max(
            scale_floor,
            1.4826 * float(np.median(np.abs(residuals - center))),
        )
        absolute = np.abs(residuals - center)
        cutoff = config.huber_tuning * scale
        weights = np.where(absolute <= cutoff, 1.0, cutoff / np.maximum(absolute, 1e-30))
        root_weight = np.sqrt(weights)
        updated = np.linalg.lstsq(design * root_weight[:, None], values * root_weight, rcond=None)[
            0
        ]
        if np.allclose(updated, coefficients, rtol=0.0, atol=1e-15):
            coefficients = updated
            break
        coefficients = updated
    residuals = _residual(values, design @ coefficients, circular_period_s)
    center = float(np.median(residuals))
    scale = max(scale_floor, 1.4826 * float(np.median(np.abs(residuals - center))))
    inliers = np.abs(residuals - center) <= config.outlier_scale * scale
    return coefficients.astype(np.float64), scale, inliers


def _least_squares_coefficients(
    times_s: npt.NDArray[np.float64],
    values: npt.NDArray[np.float64],
    *,
    degree: int,
) -> npt.NDArray[np.float64]:
    return np.linalg.lstsq(_design(times_s, degree), values, rcond=None)[0].astype(np.float64)


def _design(times_s: npt.NDArray[np.float64], degree: int) -> npt.NDArray[np.float64]:
    if degree == 1:
        return np.column_stack((np.ones(len(times_s)), times_s))
    if degree == 2:
        return np.column_stack((np.ones(len(times_s)), times_s, 0.5 * times_s**2))
    raise ValueError("GLRT epoch polynomial degree must be one or two")


def _evaluate(
    coefficients: npt.NDArray[np.float64], times_s: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    return _design(times_s, len(coefficients) - 1) @ coefficients


def _residual(
    observed: npt.NDArray[np.float64],
    predicted: npt.NDArray[np.float64],
    circular_period_s: float | None,
) -> npt.NDArray[np.float64]:
    return (
        observed - predicted
        if circular_period_s is None
        else _circular_residual(observed, predicted, period_s=circular_period_s)
    )


def _circular_residual(
    observed: npt.NDArray[np.float64],
    predicted: npt.NDArray[np.float64],
    *,
    period_s: float = _FRAME_PERIOD_S,
) -> npt.NDArray[np.float64]:
    return (observed - predicted + period_s / 2.0) % period_s - period_s / 2.0


def _polynomial_contract(
    *,
    degree: int,
    coefficients: npt.NDArray[np.float64],
    reference_time_s: float,
    residuals_s: npt.NDArray[np.float64],
    local_times_s: npt.NDArray[np.float64],
    rf_reference_hz: float,
) -> NativeGlrtEpochPolynomialFitV1:
    curvature = 0.0 if degree == 1 else float(coefficients[2])
    design = _design(local_times_s, degree)
    degrees_of_freedom = max(1, len(residuals_s) - len(coefficients))
    variance = float(np.dot(residuals_s, residuals_s) / degrees_of_freedom)
    covariance = np.linalg.pinv(design.T @ design) * variance
    drift_sigma = float(math.sqrt(max(float(covariance[1, 1]), 0.0)))
    curvature_sigma = 0.0 if degree == 1 else float(math.sqrt(max(float(covariance[2, 2]), 0.0)))
    values = {
        "polynomial_degree": degree,
        "timing_model": "phase=p0+drift*dt+0.5*curvature*dt^2",
        "point_count": len(residuals_s),
        "reference_time_s": reference_time_s,
        "phase_at_reference_s": float(coefficients[0]),
        "timing_drift_s_s": float(coefficients[1]),
        "formal_timing_drift_sigma_s_s": drift_sigma,
        "timing_curvature_s_s2": curvature,
        "formal_timing_curvature_sigma_s_s2": curvature_sigma,
        "equivalent_doppler_at_reference_hz": float(-rf_reference_hz * coefficients[1]),
        "formal_equivalent_doppler_sigma_hz": float(rf_reference_hz * drift_sigma),
        "equivalent_doppler_rate_hz_s": float(-rf_reference_hz * curvature),
        "formal_equivalent_doppler_rate_sigma_hz_s": float(rf_reference_hz * curvature_sigma),
        "residual_rms_s": float(np.sqrt(np.mean(residuals_s**2))),
        "residual_mad_scale_s": float(
            1.4826 * np.median(np.abs(residuals_s - np.median(residuals_s)))
        ),
        "maximum_absolute_residual_s": float(np.max(np.abs(residuals_s))),
    }
    return NativeGlrtEpochPolynomialFitV1.model_validate(
        {**values, "fit_digest": canonical_digest({"schema_version": 1, **values})}
    )


def render_standard_native_glrt_epoch_timing_png(
    product: StandardNativeGlrtEpochTrackingV1,
    *,
    path_label: str,
) -> bytes:
    """Render epoch phase, linear residual, and quadratic residual diagnostics."""

    with _RENDER_LOCK, plt.rc_context({"axes.grid": True, "grid.alpha": 0.22, "font.size": 10}):
        figure, axes = plt.subplots(3, 1, figsize=(16, 11), sharex=True, constrained_layout=True)
        complete = tuple(item for item in product.locklets if item.quadratic_fit is not None)
        if not complete:
            for axis in axes:
                axis.text(0.5, 0.5, "No continuity-local epoch fit met support gates", ha="center")
            figure.suptitle(
                f"{product.source.session_id} · {path_label} · GLRT frame-epoch tracking\n"
                "750 Hz receiver-relative arrival phase · continuity-local fits only"
            )
            return _save(figure)
        for index, locklet in enumerate(complete):
            color = _COLORS[index % len(_COLORS)]
            inliers = tuple(item for item in locklet.observations if item.epoch_fit_inlier)
            excluded = tuple(item for item in locklet.observations if not item.epoch_fit_inlier)
            times = np.asarray([item.global_center_time_s for item in inliers])
            phase = np.asarray([item.unwrapped_frame_phase_s for item in inliers])
            linear = locklet.linear_fit
            quadratic = locklet.quadratic_fit
            assert linear is not None and quadratic is not None
            local = times - linear.reference_time_s
            linear_prediction = linear.phase_at_reference_s + linear.timing_drift_s_s * local
            quadratic_prediction = (
                quadratic.phase_at_reference_s
                + quadratic.timing_drift_s_s * local
                + 0.5 * quadratic.timing_curvature_s_s2 * local**2
            )
            label = f"segment {locklet.continuity_segment_index} · locklet {locklet.locklet_index}"
            axes[0].scatter(times, phase * 1e6, s=6, color=color, alpha=0.45)
            axes[0].plot(times, linear_prediction * 1e6, color=color, linestyle="--")
            axes[0].plot(times, quadratic_prediction * 1e6, color=color, label=label)
            axes[1].scatter(
                times,
                [cast(float, item.linear_residual_s) * 1e6 for item in inliers],
                s=6,
                color=color,
                alpha=0.55,
            )
            axes[2].scatter(
                times,
                [cast(float, item.quadratic_residual_s) * 1e6 for item in inliers],
                s=6,
                color=color,
                alpha=0.55,
            )
            if excluded:
                axes[0].scatter(
                    [item.global_center_time_s for item in excluded],
                    [item.unwrapped_frame_phase_s * 1e6 for item in excluded],
                    s=5,
                    color="#9ca3af",
                    alpha=0.25,
                )
        axes[0].set_ylabel("Unwrapped frame phase (µs)")
        axes[0].set_title("A · CFO-selected 750 Hz frame epochs with linear and quadratic fits")
        axes[0].legend(loc="best", fontsize=8)
        axes[1].axhline(0.0, color="#111827", linewidth=0.8)
        axes[1].set_ylabel("Linear residual (µs)")
        axes[1].set_title("B · Linear timing residual")
        axes[2].axhline(0.0, color="#111827", linewidth=0.8)
        axes[2].set_ylabel("Quadratic residual (µs)")
        axes[2].set_xlabel("Global device-axis time (s)")
        axes[2].set_title("C · Quadratic timing residual")
        figure.suptitle(
            f"{product.source.session_id} · {path_label} · receiver-relative GLRT epoch tracking\n"
            "750 Hz arrival phase · overlapping-window formal uncertainties are optimistic"
        )
        return _save(figure)


def render_standard_native_glrt_epoch_rate_png(
    product: StandardNativeGlrtEpochTrackingV1,
    *,
    path_label: str,
) -> bytes:
    """Compare epoch-derived frequency/rate changes with the CFO-selected branch."""

    with _RENDER_LOCK, plt.rc_context({"axes.grid": True, "grid.alpha": 0.22, "font.size": 10}):
        figure, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True, constrained_layout=True)
        rf_reference_ghz = product.rf_reference_hz / 1e9
        complete = tuple(item for item in product.locklets if item.quadratic_fit is not None)
        if not complete:
            for axis in axes:
                axis.text(0.5, 0.5, "No continuity-local epoch fit met support gates", ha="center")
            figure.suptitle(
                f"{product.source.session_id} · {path_label} · GLRT epoch Doppler rate\n"
                f"equivalent Doppler = -{rf_reference_ghz:.6f} GHz × arrival-phase rate"
            )
            return _save(figure)
        for index, locklet in enumerate(complete):
            color = _COLORS[index % len(_COLORS)]
            epoch_fit = locklet.quadratic_fit
            selection = locklet.cfo_selection
            assert (
                epoch_fit is not None
                and selection.quadratic_coefficients_hz is not None
                and selection.reference_time_s is not None
            )
            times = np.linspace(locklet.global_start_time_s, locklet.global_end_time_s, 300)
            epoch_local = times - epoch_fit.reference_time_s
            epoch_change_hz = (
                -product.rf_reference_hz * epoch_fit.timing_curvature_s_s2 * epoch_local
            )
            cfo_local = times - selection.reference_time_s
            cfo_coefficients = selection.quadratic_coefficients_hz
            cfo_curve = (
                cfo_coefficients[0]
                + cfo_coefficients[1] * cfo_local
                + 0.5 * cfo_coefficients[2] * cfo_local**2
            )
            cfo_at_epoch_reference = (
                cfo_coefficients[0]
                + cfo_coefficients[1] * (epoch_fit.reference_time_s - selection.reference_time_s)
                + 0.5
                * cfo_coefficients[2]
                * (epoch_fit.reference_time_s - selection.reference_time_s) ** 2
            )
            label = f"segment {locklet.continuity_segment_index} · locklet {locklet.locklet_index}"
            axes[0].plot(times, epoch_change_hz / 1e3, color=color, label=f"epoch · {label}")
            axes[0].plot(
                times,
                (cfo_curve - cfo_at_epoch_reference) / 1e3,
                color=color,
                linestyle="--",
                label=f"CFO · {label}",
            )
            epoch_rate = epoch_fit.equivalent_doppler_rate_hz_s
            cfo_rate = cfo_coefficients[1] + cfo_coefficients[2] * cfo_local
            axes[1].plot(times, np.full_like(times, epoch_rate) / 1e3, color=color)
            axes[1].plot(times, cfo_rate / 1e3, color=color, linestyle="--")
        axes[0].axhline(0.0, color="#111827", linewidth=0.8)
        axes[0].set_ylabel("Change from epoch-fit reference (kHz)")
        axes[0].set_title(
            "A · Arrival-epoch-equivalent Doppler change (solid) versus canonical CFO (dashed)"
        )
        axes[0].legend(loc="best", fontsize=8, ncol=2)
        axes[1].set_ylabel("Doppler rate (kHz/s)")
        axes[1].set_xlabel("Global device-axis time (s)")
        axes[1].set_title("B · Epoch curvature rate (solid) versus CFO derivative (dashed)")
        figure.suptitle(
            f"{product.source.session_id} · {path_label} · GLRT epoch/CFO rate consistency\n"
            f"physical arrival-time sign: equivalent Doppler = -{rf_reference_ghz:.6f} GHz × "
            "phase rate"
        )
        return _save(figure)


def _save(figure: Any) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=150, metadata={"Software": "leo-tracker"})
    plt.close(figure)
    return buffer.getvalue()
