"""Grouped circular-frequency likelihood proxy for multiscan localization.

Generative interpretation
-------------------------
Each raw source group is one observation.  It first draws one stored row
alternative from a frozen within-group categorical distribution.  It then
draws either the explicit uniform null component, with density ``1/alias_hz``,
or one satellite identity.  A satellite emits a wrapped-normal frequency
residual when that row/candidate is visible and has zero signal density when
it is invisible.  The signal mixture weights sum to one and share the mass
``1 - background_mass``; the null receives ``background_mass``.

Rows within a group are marginalized, never multiplied as independent
evidence.  With no supplied row weights, observationally identical rows are
collapsed and unique alternatives receive equal mass.  Supplied row weights
are normalized within each group and are treated as frozen categorical mass.

This is a likelihood proxy, not a calibrated posterior: stored GLRT
alternatives are correlated and their selection process is not represented by
the wrapped Gaussian or uniform null.
"""

from __future__ import annotations

import numpy as np

DEFAULT_ALIAS_HZ = 1.0 / 4.4e-6
_LOG_2PI = float(np.log(2 * np.pi))


def _logsumexp(values, axis=None):
    values = np.asarray(values, dtype=float)
    maximum = np.max(values, axis=axis, keepdims=True)
    finite = np.isfinite(maximum)
    with np.errstate(invalid="ignore", divide="ignore"):
        shifted = np.where(finite, values - maximum, -np.inf)
        total = np.sum(np.exp(shifted), axis=axis, keepdims=True)
        result = np.where(finite, maximum + np.log(total), -np.inf)
    if axis is None:
        return float(result.reshape(()))
    return np.squeeze(result, axis=axis)


def circular_residual(measured, predicted=0.0, alias_hz=DEFAULT_ALIAS_HZ):
    """Return residuals in the half-open interval ``[-alias/2, alias/2)``."""

    if not np.isfinite(alias_hz) or alias_hz <= 0:
        raise ValueError("alias_hz must be positive and finite")
    return (np.asarray(measured) - np.asarray(predicted) + alias_hz / 2) % alias_hz - alias_hz / 2


def _sigma_columns(sigma_hz, satellite_count):
    values = np.asarray(sigma_hz, dtype=float)
    if values.ndim == 0:
        value = float(values)
        if not np.isfinite(value) or value <= 0:
            raise ValueError("sigma_hz must be positive and finite")
        return value, True
    if values.shape != (satellite_count,):
        raise ValueError("sigma_hz must be scalar or have one entry per prediction column")
    if np.any(~np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("sigma_hz must be positive and finite")
    return values, False


def _wrapped_normal_terms(
    residual, sigma_hz, alias_hz, chunk_size, return_prediction_gradient
):
    residual = np.asarray(residual, dtype=float)
    if residual.ndim != 2:
        raise ValueError("wrapped-normal residuals must be a two-dimensional matrix")
    if not isinstance(chunk_size, (int, np.integer)) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    sigma_hz, scalar_sigma = _sigma_columns(sigma_hz, residual.shape[1])
    tail_standard_deviations = np.sqrt(-2 * np.log(1e-15))
    image_count = max(
        1,
        int(
            np.ceil(
                (np.max(sigma_hz) * tail_standard_deviations + alias_hz / 2)
                / alias_hz
            )
        ),
    )
    images = np.arange(-image_count, image_count + 1, dtype=float) * alias_hz
    output = np.empty(residual.shape, dtype=float)
    prediction_gradient = np.empty(residual.shape, dtype=float) if return_prediction_gradient else None
    if scalar_sigma:
        normalizer = np.log(sigma_hz) + 0.5 * _LOG_2PI
        sigma_squared = sigma_hz**2
    else:
        normalizer = np.log(sigma_hz)[None, :, None] + 0.5 * _LOG_2PI
        sigma_squared = sigma_hz[None, :, None] ** 2
    for start in range(0, len(residual), int(chunk_size)):
        stop = min(start + int(chunk_size), len(residual))
        shifted = residual[start:stop, :, None] + images
        if scalar_sigma:
            log_images = -0.5 * (shifted / sigma_hz) ** 2 - normalizer
        else:
            log_images = -0.5 * shifted**2 / sigma_squared - normalizer
        log_density = _logsumexp(log_images, axis=2)
        output[start:stop] = log_density
        if return_prediction_gradient:
            image_posterior = np.exp(log_images - log_density[:, :, None])
            if scalar_sigma:
                prediction_gradient[start:stop] = (
                    np.sum(image_posterior * shifted, axis=2) / sigma_squared
                )
            else:
                prediction_gradient[start:stop] = np.sum(
                    image_posterior * shifted / sigma_squared, axis=2
                )
    return output, prediction_gradient


def _wrapped_normal_logpdf(residual, sigma_hz, alias_hz, chunk_size):
    return _wrapped_normal_terms(
        residual, sigma_hz, alias_hz, chunk_size, False
    )[0]


def _validate_mixture_parameters(
    satellite_count, satellite_weights, background_mass, alias_hz
):
    if not np.isfinite(alias_hz) or alias_hz <= 0:
        raise ValueError("alias_hz must be positive and finite")
    if not np.isfinite(background_mass) or not 0 < background_mass <= 1:
        raise ValueError("background_mass must lie in (0, 1]")
    satellite_weights = np.asarray(satellite_weights, dtype=float)
    if satellite_weights.shape != (satellite_count,):
        raise ValueError("satellite_weights must have one entry per prediction column")
    if np.any(~np.isfinite(satellite_weights)) or np.any(satellite_weights < 0):
        raise ValueError("satellite_weights must be finite and non-negative")
    weight_sum = float(np.sum(satellite_weights))
    if not np.isclose(weight_sum, 1.0, rtol=0, atol=1e-12):
        raise ValueError("satellite_weights must lie on the unit simplex")
    return satellite_weights / weight_sum


def _mixture_result(
    groups,
    group_log_signal,
    satellite_weights,
    background_mass,
    alias_hz,
    alternative_count,
    unique_alternative_count,
):
    with np.errstate(divide="ignore"):
        log_satellite_weights = np.where(
            satellite_weights > 0, np.log(satellite_weights), -np.inf
        )
    log_signal_mass = -np.inf if background_mass == 1 else np.log1p(-background_mass)
    satellite_components = (
        log_signal_mass + log_satellite_weights[None, :] + group_log_signal
    )
    null_component = np.full(len(groups), np.log(background_mass) - np.log(alias_hz))
    log_likelihood = np.logaddexp(
        null_component,
        _logsumexp(satellite_components, axis=1),
    )
    satellite_responsibility = np.exp(satellite_components - log_likelihood[:, None])
    null_responsibility = np.exp(null_component - log_likelihood)
    return {
        "group_values": groups,
        "log_likelihood": log_likelihood,
        "total_log_likelihood": float(np.sum(log_likelihood)),
        "satellite_responsibility": satellite_responsibility,
        "null_responsibility": null_responsibility,
        "satellite_support": np.sum(satellite_responsibility, axis=0),
        "null_support": float(np.sum(null_responsibility)),
        "alternative_count": alternative_count,
        "unique_alternative_count": unique_alternative_count,
        "alias_hz": float(alias_hz),
        "background_mass": float(background_mass),
    }


def _validate_inputs(
    measured,
    predicted,
    visible,
    group,
    row_weights,
    satellite_weights,
    background_mass,
    alias_hz,
):
    measured = np.asarray(measured, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    group = np.asarray(group)
    if measured.ndim != 1 or group.ndim != 1:
        raise ValueError("measured and group must be one-dimensional")
    if predicted.ndim != 2 or visible.shape != predicted.shape:
        raise ValueError("predicted and visible must be equally shaped row-by-satellite matrices")
    if len(measured) == 0 or len(measured) != len(group) or len(measured) != len(predicted):
        raise ValueError("all row inputs must have one equal nonzero length")
    if predicted.shape[1] == 0:
        raise ValueError("at least one satellite trajectory is required")
    if not np.all(np.isfinite(measured)):
        raise ValueError("measured must be finite")
    if np.any(visible & ~np.isfinite(predicted)):
        raise ValueError("visible predictions must be finite")
    satellite_weights = _validate_mixture_parameters(
        predicted.shape[1], satellite_weights, background_mass, alias_hz
    )
    if row_weights is not None:
        row_weights = np.asarray(row_weights, dtype=float)
        if row_weights.shape != measured.shape:
            raise ValueError("row_weights must match measured")
        if np.any(~np.isfinite(row_weights)) or np.any(row_weights < 0):
            raise ValueError("row_weights must be finite and non-negative")
    return measured, predicted, visible, group, row_weights, satellite_weights


class PreparedGroupedLikelihood:
    """Frozen grouping and row-alternative masses for repeated evaluations.

    Construction requires explicit candidate-independent ``row_weights``.
    Candidate-dependent duplicate detection is intentionally absent: callers
    must deduplicate observed event features once, freeze that policy, and
    encode it in these weights before optimization.  This avoids silently
    changing the default API's candidate-dependent deduplication semantics.
    """

    def __init__(self, measured, group, row_weights, alias_hz):
        measured = np.asarray(measured, dtype=float)
        group = np.asarray(group)
        row_weights = np.asarray(row_weights, dtype=float)
        if measured.ndim != 1 or group.ndim != 1 or row_weights.ndim != 1:
            raise ValueError("measured, group, and row_weights must be one-dimensional")
        if len(measured) == 0 or len(group) != len(measured) or len(row_weights) != len(measured):
            raise ValueError("prepared row inputs must have one equal nonzero length")
        if np.any(~np.isfinite(measured)):
            raise ValueError("measured must be finite")
        if np.any(~np.isfinite(row_weights)) or np.any(row_weights < 0):
            raise ValueError("row_weights must be finite and non-negative")
        if not np.isfinite(alias_hz) or alias_hz <= 0:
            raise ValueError("alias_hz must be positive and finite")

        groups, inverse = np.unique(group, return_inverse=True)
        order = np.argsort(inverse, kind="stable")
        group_counts = np.bincount(inverse, minlength=len(groups))
        group_starts = np.r_[0, np.cumsum(group_counts[:-1])]
        sorted_weights = row_weights[order]
        group_weight = np.add.reduceat(sorted_weights, group_starts)
        if np.any(group_weight <= 0):
            bad = int(np.flatnonzero(group_weight <= 0)[0])
            raise ValueError(f"row_weights have zero mass in group {groups[bad]!r}")
        owners = np.repeat(np.arange(len(groups)), group_counts)
        normalized_weights = sorted_weights / group_weight[owners]
        with np.errstate(divide="ignore"):
            log_row_weights = np.where(
                normalized_weights > 0, np.log(normalized_weights), -np.inf
            )

        self.measured = measured[order].copy()
        self.group_values = groups.copy()
        self.order = order
        self.group_starts = group_starts
        self.group_counts = group_counts
        self.group_owners = owners
        self.log_row_weights = log_row_weights
        self.alias_hz = float(alias_hz)
        for value in (
            self.measured,
            self.group_values,
            self.order,
            self.group_starts,
            self.group_counts,
            self.group_owners,
            self.log_row_weights,
        ):
            value.setflags(write=False)

    @property
    def row_count(self):
        return len(self.measured)

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        satellite_weights,
        background_mass,
        chunk_size=4096,
        return_gradient=False,
        return_precision=False,
    ):
        """Evaluate trajectories and optionally differentiate their total log likelihood.

        When requested, ``prediction_gradient`` has the original ``predicted``
        row order and contains derivatives with respect to each prediction.
        Visibility is treated as fixed for this derivative.
        """

        predicted = np.asarray(predicted, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        if predicted.ndim != 2 or predicted.shape[0] != self.row_count:
            raise ValueError("predicted must have prepared rows by satellite columns")
        if visible.shape != predicted.shape:
            raise ValueError("visible must match predicted")
        if predicted.shape[1] == 0:
            raise ValueError("at least one satellite trajectory is required")
        if np.any(visible & ~np.isfinite(predicted)):
            raise ValueError("visible predictions must be finite")
        satellite_weights = _validate_mixture_parameters(
            predicted.shape[1],
            satellite_weights,
            background_mass,
            self.alias_hz,
        )
        sigma_hz, scalar_sigma = _sigma_columns(sigma_hz, predicted.shape[1])
        if not isinstance(chunk_size, (int, np.integer)) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")

        if background_mass == 1:
            group_log_signal = np.full(
                (len(self.group_values), predicted.shape[1]), -np.inf
            )
            prediction_gradient = np.zeros_like(predicted) if return_gradient else None
            prediction_precision = np.zeros_like(predicted) if return_precision else None
        else:
            ordered_prediction = predicted[self.order]
            ordered_visible = visible[self.order]
            residual = circular_residual(
                self.measured[:, None], ordered_prediction, self.alias_hz
            )
            residual = np.where(ordered_visible, residual, 0.0)
            log_density, log_density_prediction_gradient = _wrapped_normal_terms(
                residual,
                sigma_hz,
                self.alias_hz,
                chunk_size,
                return_gradient,
            )
            weighted = np.where(
                ordered_visible,
                log_density + self.log_row_weights[:, None],
                -np.inf,
            )
            maximum = np.maximum.reduceat(weighted, self.group_starts, axis=0)
            finite = np.isfinite(maximum)
            with np.errstate(invalid="ignore", divide="ignore"):
                shifted = np.where(
                    finite[self.group_owners],
                    weighted - maximum[self.group_owners],
                    -np.inf,
                )
                total = np.add.reduceat(np.exp(shifted), self.group_starts, axis=0)
                group_log_signal = np.where(finite, maximum + np.log(total), -np.inf)

        result = _mixture_result(
            self.group_values,
            group_log_signal,
            satellite_weights,
            background_mass,
            self.alias_hz,
            self.group_counts.copy(),
            self.group_counts.copy(),
        )
        result["sigma_hz"] = float(sigma_hz) if scalar_sigma else sigma_hz.copy()
        result["prepared_fixed_row_weights"] = True
        if (return_gradient or return_precision) and background_mass < 1:
            row_group_log_signal = group_log_signal[self.group_owners]
            row_responsibility = np.zeros_like(weighted)
            usable = ordered_visible & np.isfinite(row_group_log_signal)
            row_responsibility[usable] = np.exp(
                weighted[usable] - row_group_log_signal[usable]
            )
            ordered_signal_mass = (
                result["satellite_responsibility"][self.group_owners]
                * row_responsibility
            )
            if return_gradient:
                ordered_gradient = ordered_signal_mass * log_density_prediction_gradient
                prediction_gradient = np.empty_like(ordered_gradient)
                prediction_gradient[self.order] = ordered_gradient
            if return_precision:
                sigma_squared = sigma_hz**2 if scalar_sigma else sigma_hz[None, :] ** 2
                ordered_precision = ordered_signal_mass / sigma_squared
                prediction_precision = np.empty_like(ordered_precision)
                prediction_precision[self.order] = ordered_precision
        if return_gradient:
            result["prediction_gradient"] = prediction_gradient
        if return_precision:
            result["prediction_precision"] = prediction_precision
        return result


def prepare_grouped_likelihood(
    measured,
    group,
    *,
    row_weights,
    alias_hz=DEFAULT_ALIAS_HZ,
):
    """Freeze grouping and explicit candidate-independent row weights."""

    return PreparedGroupedLikelihood(measured, group, row_weights, alias_hz)


def _default_unique_rows(group_rows, residual, visible):
    signature = np.concatenate(
        (
            np.where(visible[group_rows], residual[group_rows], 0.0),
            visible[group_rows].astype(float),
        ),
        axis=1,
    )
    _, first = np.unique(signature, axis=0, return_index=True)
    return group_rows[np.sort(first)]


def grouped_mixture_likelihood(
    measured,
    predicted,
    visible,
    group,
    *,
    sigma_hz,
    satellite_weights,
    background_mass,
    row_weights=None,
    alias_hz=DEFAULT_ALIAS_HZ,
    chunk_size=4096,
):
    """Evaluate one normalized mixture likelihood per raw source group.

    Invisible signal components retain their satellite and row-alternative
    prior mass but contribute zero density.  They are not removed and the
    remaining components are not renormalized, preserving detection penalties.
    The positive explicit null mass therefore keeps every group finite,
    including groups for which all satellite trajectories are invisible.
    """

    (
        measured,
        predicted,
        visible,
        group,
        row_weights,
        satellite_weights,
    ) = _validate_inputs(
        measured,
        predicted,
        visible,
        group,
        row_weights,
        satellite_weights,
        background_mass,
        alias_hz,
    )
    groups, inverse = np.unique(group, return_inverse=True)
    residual = circular_residual(measured[:, None], predicted, alias_hz)
    log_density = _wrapped_normal_logpdf(residual, sigma_hz, alias_hz, chunk_size)
    log_density = np.where(visible, log_density, -np.inf)
    group_log_signal = np.full((len(groups), predicted.shape[1]), -np.inf)
    alternative_count = np.zeros(len(groups), dtype=int)
    unique_alternative_count = np.zeros(len(groups), dtype=int)
    grouped_order = np.argsort(inverse, kind="stable")
    group_counts = np.bincount(inverse, minlength=len(groups))
    group_starts = np.r_[0, np.cumsum(group_counts[:-1])]
    for group_index in range(len(groups)):
        start = group_starts[group_index]
        rows = grouped_order[start : start + group_counts[group_index]]
        alternative_count[group_index] = len(rows)
        unique_rows = _default_unique_rows(rows, residual, visible)
        unique_alternative_count[group_index] = len(unique_rows)
        if row_weights is None:
            log_alternative = np.full(len(unique_rows), -np.log(len(unique_rows)))
            local_rows = unique_rows
        else:
            total = float(np.sum(row_weights[rows]))
            if total <= 0:
                raise ValueError(f"row_weights have zero mass in group {groups[group_index]!r}")
            with np.errstate(divide="ignore"):
                log_alternative = np.where(
                    row_weights[rows] > 0,
                    np.log(row_weights[rows] / total),
                    -np.inf,
                )
            local_rows = rows
        group_log_signal[group_index] = _logsumexp(
            log_density[local_rows] + log_alternative[:, None], axis=0
        )

    result = _mixture_result(
        groups,
        group_log_signal,
        satellite_weights,
        background_mass,
        alias_hz,
        alternative_count,
        unique_alternative_count,
    )
    sigma_hz, scalar_sigma = _sigma_columns(sigma_hz, predicted.shape[1])
    result["sigma_hz"] = float(sigma_hz) if scalar_sigma else sigma_hz.copy()
    return result


def gaussian_tau_log_prior(tau_s, sigma_s, *, mean_s=0.0):
    """Return the normalized joint Gaussian log density for timing offsets."""

    tau_s = np.asarray(tau_s, dtype=float)
    mean_s = np.asarray(mean_s, dtype=float)
    if np.any(~np.isfinite(tau_s)) or np.any(~np.isfinite(mean_s)):
        raise ValueError("tau_s and mean_s must be finite")
    if not np.isfinite(sigma_s) or sigma_s <= 0:
        raise ValueError("sigma_s must be positive and finite")
    standardized = (tau_s - mean_s) / sigma_s
    return float(
        -0.5 * np.sum(standardized**2)
        - tau_s.size * (np.log(sigma_s) + 0.5 * _LOG_2PI)
    )


def parsimonious_model_score(
    group_log_likelihood,
    *,
    complexity_penalty,
    tau_s=None,
    tau_sigma_s=None,
    tau_mean_s=0.0,
):
    """Combine grouped evidence, an optional timing prior, and an explicit penalty.

    This helper scores one already-specified model.  It does not choose a
    satellite count, construct a penalty from reference truth, or compare a
    data-dependent candidate ladder.  The caller must supply the complete
    non-negative complexity penalty and apply one frozen comparison policy.
    """

    group_log_likelihood = np.asarray(group_log_likelihood, dtype=float)
    if group_log_likelihood.ndim != 1 or np.any(~np.isfinite(group_log_likelihood)):
        raise ValueError("group_log_likelihood must be a finite one-dimensional vector")
    if not np.isfinite(complexity_penalty) or complexity_penalty < 0:
        raise ValueError("complexity_penalty must be non-negative and finite")
    if tau_s is None:
        if tau_sigma_s is not None:
            raise ValueError("tau_sigma_s requires tau_s")
        timing_log_prior = 0.0
    else:
        if tau_sigma_s is None:
            raise ValueError("tau_s requires tau_sigma_s")
        timing_log_prior = gaussian_tau_log_prior(
            tau_s, tau_sigma_s, mean_s=tau_mean_s
        )
    likelihood = float(np.sum(group_log_likelihood))
    return {
        "score": likelihood + timing_log_prior - float(complexity_penalty),
        "group_log_likelihood": likelihood,
        "timing_log_prior": timing_log_prior,
        "complexity_penalty": float(complexity_penalty),
        "groups": int(len(group_log_likelihood)),
    }


__all__ = [
    "DEFAULT_ALIAS_HZ",
    "PreparedGroupedLikelihood",
    "circular_residual",
    "gaussian_tau_log_prior",
    "grouped_mixture_likelihood",
    "parsimonious_model_score",
    "prepare_grouped_likelihood",
]
