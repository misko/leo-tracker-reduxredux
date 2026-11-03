"""Finite-set circular-frequency likelihood for one or more peaks per probe.

Each visible satellite independently produces at most one peak with fixed
detection probability.  Clutter is a Poisson process with uniform frequency
on the alias interval.  Associations are injective in both directions.  The
model is conditioned on a nonempty set because persisted source groups contain
at least one peak.

The Poisson clutter model is an approximation to candidate production.  It
does not assert that peaks extracted from shared IQ are physically independent.
It is exact over the supplied peak set; upstream top-eight peak censoring is not
modeled.

The returned likelihood is the standard unlabeled finite-set density.  The
Poisson ``1/c!`` count factor cancels the ``c!`` permutations of clutter points;
the finite-set integral itself carries ``1/n!``.  Rows are observed peaks, not
categorical alternatives, so there is no row-weight port.  Exact-period copies
are collapsed with equal, candidate-independent metadata weight.
"""

from __future__ import annotations

import numpy as np

DEFAULT_ALIAS_HZ = 1.0 / 4.4e-6
DEFAULT_MAX_PEAKS_PER_GROUP = 8
DEFAULT_MAX_DP_CELLS = 1_000_000
DEFAULT_MAX_BATCH_DP_CELLS = 2_000_000
_LOG_2PI = float(np.log(2 * np.pi))


def circular_residual(measured, predicted=0.0, alias_hz=DEFAULT_ALIAS_HZ):
    """Return residuals in the half-open interval ``[-alias/2, alias/2)``."""

    if not np.isfinite(alias_hz) or alias_hz <= 0:
        raise ValueError("alias_hz must be positive and finite")
    return (np.asarray(measured) - np.asarray(predicted) + alias_hz / 2) % alias_hz - alias_hz / 2


def _logsumexp(values):
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return -np.inf
    maximum = float(np.max(values))
    if not np.isfinite(maximum):
        return maximum
    return maximum + float(np.log(np.sum(np.exp(values - maximum))))


def _logsumexp_axis(values, axis):
    values = np.asarray(values, dtype=float)
    maximum = np.max(values, axis=axis, keepdims=True)
    finite = np.isfinite(maximum)
    with np.errstate(invalid="ignore", divide="ignore"):
        shifted = np.where(finite, values - maximum, -np.inf)
        result = np.where(
            finite,
            maximum + np.log(np.sum(np.exp(shifted), axis=axis, keepdims=True)),
            -np.inf,
        )
    return np.squeeze(result, axis=axis)


def _wrapped_normal_terms(residual, sigma_hz, alias_hz, chunk_size, return_gradient):
    residual = np.asarray(residual, dtype=float)
    if residual.ndim != 2:
        raise ValueError("residual must be a row-by-satellite matrix")
    tail_standard_deviations = np.sqrt(-2 * np.log(1e-15))
    image_count = max(
        1,
        int(np.ceil((sigma_hz * tail_standard_deviations + alias_hz / 2) / alias_hz)),
    )
    images = np.arange(-image_count, image_count + 1, dtype=float) * alias_hz
    log_density = np.empty_like(residual)
    gradient = np.empty_like(residual) if return_gradient else None
    for start in range(0, len(residual), chunk_size):
        stop = min(start + chunk_size, len(residual))
        shifted = residual[start:stop, :, None] + images
        log_images = -0.5 * (shifted / sigma_hz) ** 2 - np.log(sigma_hz) - 0.5 * _LOG_2PI
        maximum = np.max(log_images, axis=2, keepdims=True)
        chunk_density = np.squeeze(
            maximum + np.log(np.sum(np.exp(log_images - maximum), axis=2, keepdims=True)),
            axis=2,
        )
        log_density[start:stop] = chunk_density
        if return_gradient:
            image_probability = np.exp(log_images - chunk_density[:, :, None])
            gradient[start:stop] = np.sum(image_probability * shifted, axis=2) / sigma_hz**2
    return log_density, gradient


def _validate_probability(value, name):
    if not np.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must lie in [0, 1]")
    return float(value)


def _detection_probabilities(value, satellite_count):
    probabilities = np.asarray(value, dtype=float)
    if probabilities.ndim == 0:
        probabilities = np.full(satellite_count, float(probabilities))
    if probabilities.shape != (satellite_count,):
        raise ValueError("detection_probability must be scalar or have one entry per satellite")
    for probability in probabilities:
        _validate_probability(probability, "detection_probability")
    return probabilities


def _period_equivalent(left, right, alias_hz):
    tolerance = 8 * np.finfo(float).eps * max(alias_hz, abs(float(left)), abs(float(right)), 1.0)
    return abs(float(circular_residual(left, right, alias_hz))) <= tolerance


def _deduplicate_group(measured, indices, alias_hz):
    canonical = circular_residual(measured[indices], 0.0, alias_hz)
    ordered = indices[np.argsort(canonical, kind="stable")]
    clusters = []
    for index in ordered:
        for cluster in clusters:
            if _period_equivalent(measured[index], measured[cluster[0]], alias_hz):
                cluster.append(int(index))
                break
        else:
            clusters.append([int(index)])
    clusters.sort(key=lambda cluster: float(circular_residual(measured[cluster[0]], 0.0, alias_hz)))
    return tuple(np.asarray(cluster, dtype=np.int64) for cluster in clusters)


def _subset_indices(peak_count):
    masks = np.arange(1 << peak_count, dtype=np.int64)
    without = []
    with_peak = []
    for peak in range(peak_count):
        available = masks[(masks & (1 << peak)) == 0]
        without.append(available)
        with_peak.append(available | (1 << peak))
    return masks, tuple(without), tuple(with_peak)


def _finite_set_group(
    log_density,
    visible,
    detection_probability,
    clutter_rate,
    alias_hz,
    max_dp_cells,
):
    peak_count, satellite_count = log_density.shape
    state_count = 1 << peak_count
    required_cells = 2 * (satellite_count + 1) * state_count
    if required_cells > max_dp_cells:
        raise ValueError(
            f"finite-set DP requires {required_cells} cells, exceeding max_dp_cells={max_dp_cells}"
        )

    masks, without_peak, with_peak = _subset_indices(peak_count)
    cardinality = np.fromiter(
        (int(mask).bit_count() for mask in masks), dtype=np.int64, count=state_count
    )
    clutter_count = peak_count - cardinality
    log_tail = (
        -clutter_rate + clutter_count * np.log(clutter_rate) - clutter_count * np.log(alias_hz)
    )

    group_visible = np.any(visible, axis=0)
    effective_detection = np.where(group_visible, detection_probability, 0.0)
    with np.errstate(divide="ignore"):
        log_detection = np.log(effective_detection)
        log_miss = np.log1p(-effective_detection)

    forward = np.full((satellite_count + 1, state_count), -np.inf)
    forward[0, 0] = 0.0
    for satellite in range(satellite_count):
        next_row = forward[satellite] + log_miss[satellite]
        if np.isfinite(log_detection[satellite]):
            for peak in np.flatnonzero(visible[:, satellite]):
                source = without_peak[peak]
                target = with_peak[peak]
                candidate = (
                    forward[satellite, source]
                    + log_detection[satellite]
                    + log_density[peak, satellite]
                )
                next_row[target] = np.logaddexp(next_row[target], candidate)
        forward[satellite + 1] = next_row

    reverse = np.full_like(forward, -np.inf)
    reverse[satellite_count] = log_tail
    for satellite in range(satellite_count - 1, -1, -1):
        row = log_miss[satellite] + reverse[satellite + 1]
        if np.isfinite(log_detection[satellite]):
            for peak in np.flatnonzero(visible[:, satellite]):
                source = without_peak[peak]
                target = with_peak[peak]
                row[source] = np.logaddexp(
                    row[source],
                    log_detection[satellite]
                    + log_density[peak, satellite]
                    + reverse[satellite + 1, target],
                )
        reverse[satellite] = row

    log_unconditioned = float(reverse[0, 0])
    if not np.isfinite(log_unconditioned):
        raise FloatingPointError("observed finite set has zero model probability")
    log_empty = -clutter_rate + float(np.sum(log_miss))
    if log_empty >= 0:
        raise FloatingPointError("nonempty conditioning event has zero probability")
    log_nonempty = float(np.log(-np.expm1(log_empty)))

    association = np.zeros((peak_count, satellite_count))
    miss = np.zeros(satellite_count)
    for satellite in range(satellite_count):
        if np.isfinite(log_miss[satellite]):
            miss[satellite] = np.exp(
                _logsumexp(forward[satellite] + log_miss[satellite] + reverse[satellite + 1])
                - log_unconditioned
            )
        if not np.isfinite(log_detection[satellite]):
            continue
        for peak in np.flatnonzero(visible[:, satellite]):
            source = without_peak[peak]
            target = with_peak[peak]
            association[peak, satellite] = np.exp(
                _logsumexp(
                    forward[satellite, source]
                    + log_detection[satellite]
                    + log_density[peak, satellite]
                    + reverse[satellite + 1, target]
                )
                - log_unconditioned
            )

    final_log_probability = forward[satellite_count] + log_tail - log_unconditioned
    final_probability = np.exp(final_log_probability)
    clutter = np.empty(peak_count)
    for peak in range(peak_count):
        clutter[peak] = np.sum(final_probability[(masks & (1 << peak)) == 0])

    return {
        "log_likelihood": log_unconditioned - log_nonempty,
        "unconditioned_log_likelihood": log_unconditioned,
        "empty_probability": float(np.exp(log_empty)),
        "nonempty_probability": float(-np.expm1(log_empty)),
        "association_probability": association,
        "clutter_probability": clutter,
        "satellite_miss_probability": miss,
    }


def _finite_set_group_batch(
    log_density,
    visible,
    detection_probability,
    clutter_rate,
    alias_hz,
    max_dp_cells,
    max_batch_dp_cells,
):
    """Vectorized equivalent of ``_finite_set_group`` for equal-cardinality groups."""

    batch_count, peak_count, satellite_count = log_density.shape
    state_count = 1 << peak_count
    cells_per_group = 2 * (satellite_count + 1) * state_count
    if cells_per_group > max_dp_cells:
        raise ValueError(
            f"finite-set DP requires {cells_per_group} cells, exceeding max_dp_cells={max_dp_cells}"
        )
    required_cells = batch_count * cells_per_group
    if required_cells > max_batch_dp_cells:
        raise ValueError(
            f"finite-set batch requires {required_cells} cells, "
            f"exceeding max_batch_dp_cells={max_batch_dp_cells}"
        )

    masks, without_peak, with_peak = _subset_indices(peak_count)
    cardinality = np.fromiter(
        (int(mask).bit_count() for mask in masks), dtype=np.int64, count=state_count
    )
    clutter_count = peak_count - cardinality
    log_tail = (
        -clutter_rate + clutter_count * np.log(clutter_rate) - clutter_count * np.log(alias_hz)
    )

    group_visible = np.any(visible, axis=1)
    effective_detection = np.where(group_visible, detection_probability[None, :], 0.0)
    with np.errstate(divide="ignore"):
        log_detection = np.log(effective_detection)
        log_miss = np.log1p(-effective_detection)

    forward = np.full((batch_count, satellite_count + 1, state_count), -np.inf)
    forward[:, 0, 0] = 0.0
    for satellite in range(satellite_count):
        next_row = forward[:, satellite] + log_miss[:, satellite, None]
        for peak in range(peak_count):
            source = without_peak[peak]
            target = with_peak[peak]
            candidate = (
                forward[:, satellite, source]
                + log_detection[:, satellite, None]
                + log_density[:, peak, satellite, None]
            )
            candidate = np.where(visible[:, peak, satellite, None], candidate, -np.inf)
            next_row[:, target] = np.logaddexp(next_row[:, target], candidate)
        forward[:, satellite + 1] = next_row

    reverse = np.full_like(forward, -np.inf)
    reverse[:, satellite_count] = log_tail
    for satellite in range(satellite_count - 1, -1, -1):
        row = log_miss[:, satellite, None] + reverse[:, satellite + 1]
        for peak in range(peak_count):
            source = without_peak[peak]
            target = with_peak[peak]
            candidate = (
                log_detection[:, satellite, None]
                + log_density[:, peak, satellite, None]
                + reverse[:, satellite + 1, target]
            )
            candidate = np.where(visible[:, peak, satellite, None], candidate, -np.inf)
            row[:, source] = np.logaddexp(row[:, source], candidate)
        reverse[:, satellite] = row

    log_unconditioned = reverse[:, 0, 0]
    if np.any(~np.isfinite(log_unconditioned)):
        bad = int(np.flatnonzero(~np.isfinite(log_unconditioned))[0])
        raise FloatingPointError(
            f"observed finite set at batch index {bad} has zero model probability"
        )
    log_empty = -clutter_rate + np.sum(log_miss, axis=1)
    if np.any(log_empty >= 0):
        bad = int(np.flatnonzero(log_empty >= 0)[0])
        raise FloatingPointError(
            f"nonempty conditioning event at batch index {bad} has zero probability"
        )
    log_nonempty = np.log(-np.expm1(log_empty))

    association = np.zeros((batch_count, peak_count, satellite_count))
    miss = np.zeros((batch_count, satellite_count))
    for satellite in range(satellite_count):
        miss[:, satellite] = np.exp(
            _logsumexp_axis(
                forward[:, satellite] + log_miss[:, satellite, None] + reverse[:, satellite + 1],
                axis=1,
            )
            - log_unconditioned
        )
        for peak in range(peak_count):
            source = without_peak[peak]
            target = with_peak[peak]
            log_probability = _logsumexp_axis(
                forward[:, satellite, source]
                + log_detection[:, satellite, None]
                + log_density[:, peak, satellite, None]
                + reverse[:, satellite + 1, target],
                axis=1,
            )
            association[:, peak, satellite] = np.where(
                visible[:, peak, satellite],
                np.exp(log_probability - log_unconditioned),
                0.0,
            )
    miss = np.where(effective_detection == 0, 1.0, miss)

    final_probability = np.exp(
        forward[:, satellite_count] + log_tail[None, :] - log_unconditioned[:, None]
    )
    clutter = np.empty((batch_count, peak_count))
    for peak in range(peak_count):
        clutter[:, peak] = np.sum(final_probability[:, (masks & (1 << peak)) == 0], axis=1)

    return {
        "log_likelihood": log_unconditioned - log_nonempty,
        "unconditioned_log_likelihood": log_unconditioned,
        "empty_probability": np.exp(log_empty),
        "nonempty_probability": -np.expm1(log_empty),
        "association_probability": association,
        "clutter_probability": clutter,
        "satellite_miss_probability": miss,
    }


class PreparedFiniteSetLikelihood:
    """Candidate-independent grouping and exact-period duplicate partition."""

    def __init__(
        self,
        measured,
        group,
        *,
        alias_hz=DEFAULT_ALIAS_HZ,
        max_peaks_per_group=DEFAULT_MAX_PEAKS_PER_GROUP,
        max_dp_cells=DEFAULT_MAX_DP_CELLS,
        max_batch_dp_cells=DEFAULT_MAX_BATCH_DP_CELLS,
    ):
        measured = np.asarray(measured, dtype=float)
        group = np.asarray(group)
        if measured.ndim != 1 or group.ndim != 1:
            raise ValueError("measured and group must be one-dimensional")
        if len(measured) == 0 or len(group) != len(measured):
            raise ValueError("measured and group must have one equal nonzero length")
        if np.any(~np.isfinite(measured)):
            raise ValueError("measured must be finite")
        if not np.isfinite(alias_hz) or alias_hz <= 0:
            raise ValueError("alias_hz must be positive and finite")
        if not isinstance(max_peaks_per_group, (int, np.integer)) or max_peaks_per_group <= 0:
            raise ValueError("max_peaks_per_group must be a positive integer")
        if not isinstance(max_dp_cells, (int, np.integer)) or max_dp_cells <= 0:
            raise ValueError("max_dp_cells must be a positive integer")
        if not isinstance(max_batch_dp_cells, (int, np.integer)) or max_batch_dp_cells <= 0:
            raise ValueError("max_batch_dp_cells must be a positive integer")

        group_values, inverse = np.unique(group, return_inverse=True)
        clusters = []
        unique_group_index = []
        original_to_unique = np.empty(len(measured), dtype=np.int64)
        group_unique_indices = []
        group_row_indices = []
        for group_index in range(len(group_values)):
            members = np.flatnonzero(inverse == group_index)
            group_row_indices.append(members)
            group_clusters = _deduplicate_group(measured, members, alias_hz)
            if len(group_clusters) > max_peaks_per_group:
                raise ValueError(
                    f"group {group_values[group_index]!r} has {len(group_clusters)} unique "
                    f"peaks, exceeding max_peaks_per_group={max_peaks_per_group}"
                )
            unique_indices = []
            for cluster in group_clusters:
                unique_index = len(clusters)
                clusters.append(cluster)
                unique_group_index.append(group_index)
                original_to_unique[cluster] = unique_index
                unique_indices.append(unique_index)
            group_unique_indices.append(np.asarray(unique_indices, dtype=np.int64))

        self.measured = measured.copy()
        self.group_values = group_values.copy()
        self.clusters = tuple(clusters)
        self.group_unique_indices = tuple(group_unique_indices)
        self.group_row_indices = tuple(group_row_indices)
        self.unique_group_index = np.asarray(unique_group_index, dtype=np.int64)
        self.original_to_unique = original_to_unique
        self.alias_hz = float(alias_hz)
        self.max_peaks_per_group = int(max_peaks_per_group)
        self.max_dp_cells = int(max_dp_cells)
        self.max_batch_dp_cells = int(max_batch_dp_cells)
        for value in (
            self.measured,
            self.group_values,
            self.unique_group_index,
            self.original_to_unique,
            *self.clusters,
            *self.group_unique_indices,
            *self.group_row_indices,
        ):
            value.setflags(write=False)

    @property
    def row_count(self):
        return len(self.measured)

    @property
    def unique_peak_count(self):
        return len(self.clusters)

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        detection_probability,
        clutter_rate,
        chunk_size=4096,
        implementation="batched",
        return_gradient=False,
        return_precision=False,
    ):
        """Evaluate the conditioned finite-set likelihood and optional derivatives."""

        predicted = np.asarray(predicted, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        if predicted.ndim != 2 or predicted.shape[0] != self.row_count:
            raise ValueError("predicted must have prepared rows by satellite columns")
        if visible.shape != predicted.shape:
            raise ValueError("visible must match predicted")
        if np.any(visible & ~np.isfinite(predicted)):
            raise ValueError("visible predictions must be finite")
        if not np.ndim(sigma_hz) == 0 or not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("sigma_hz must be a positive finite scalar")
        sigma_hz = float(sigma_hz)
        if not np.isfinite(clutter_rate) or clutter_rate <= 0:
            raise ValueError("clutter_rate must be positive and finite")
        clutter_rate = float(clutter_rate)
        if not isinstance(chunk_size, (int, np.integer)) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        chunk_size = int(chunk_size)
        if implementation not in {"batched", "scalar"}:
            raise ValueError("implementation must be 'batched' or 'scalar'")
        satellite_count = predicted.shape[1]
        detection_probability = _detection_probabilities(detection_probability, satellite_count)

        for group_index, original_indices in enumerate(self.group_row_indices):
            group_visibility = visible[original_indices]
            if np.any(group_visibility != group_visibility[0]):
                raise ValueError(
                    "visibility must be groupwise constant for finite-set "
                    f"normalization; group {self.group_values[group_index]!r} conflicts"
                )
            group_visible = group_visibility[0]
            if np.any(group_visible):
                reference = predicted[original_indices[0]]
                difference = circular_residual(
                    predicted[original_indices], reference, self.alias_hz
                )
                tolerance = (
                    8
                    * np.finfo(float).eps
                    * np.maximum(
                        np.maximum(np.abs(predicted[original_indices]), np.abs(reference)),
                        self.alias_hz,
                    )
                )
                conflict = group_visible[None, :] & (np.abs(difference) > tolerance)
                if np.any(conflict):
                    raise ValueError(
                        "predicted means must be groupwise equal modulo alias for "
                        f"finite-set normalization; group {self.group_values[group_index]!r} "
                        "conflicts"
                    )

        if satellite_count:
            residual = circular_residual(self.measured[:, None], predicted, self.alias_hz)
            residual = np.where(visible, residual, 0.0)
            row_log_density, row_log_gradient = _wrapped_normal_terms(
                residual,
                sigma_hz,
                self.alias_hz,
                chunk_size,
                return_gradient,
            )
            row_log_density = np.where(visible, row_log_density, -np.inf)
        else:
            row_log_density = np.empty((self.row_count, 0))
            row_log_gradient = np.empty((self.row_count, 0)) if return_gradient else None

        unique_log_density = np.full((self.unique_peak_count, satellite_count), -np.inf)
        unique_visible = np.zeros_like(unique_log_density, dtype=bool)
        member_probability = np.zeros_like(row_log_density)
        singleton_unique = np.asarray(
            [index for index, members in enumerate(self.clusters) if len(members) == 1],
            dtype=np.int64,
        )
        singleton_rows = np.asarray(
            [self.clusters[index][0] for index in singleton_unique], dtype=np.int64
        )
        unique_log_density[singleton_unique] = row_log_density[singleton_rows]
        unique_visible[singleton_unique] = visible[singleton_rows]
        member_probability[singleton_rows] = visible[singleton_rows]
        for unique_index, members in enumerate(self.clusters):
            if len(members) == 1:
                continue
            for satellite in range(satellite_count):
                log_values = row_log_density[members, satellite]
                log_total = _logsumexp(log_values)
                if not np.isfinite(log_total):
                    continue
                unique_visible[unique_index, satellite] = True
                unique_log_density[unique_index, satellite] = log_total - np.log(len(members))
                finite = np.isfinite(log_values)
                member_probability[members[finite], satellite] = np.exp(
                    log_values[finite] - log_total
                )

        group_count = len(self.group_values)
        log_likelihood = np.empty(group_count)
        unconditioned_log_likelihood = np.empty(group_count)
        empty_probability = np.empty(group_count)
        nonempty_probability = np.empty(group_count)
        association = np.zeros_like(unique_log_density)
        clutter = np.zeros(self.unique_peak_count)
        miss = np.zeros((group_count, satellite_count))
        if implementation == "scalar":
            for group_index, unique_indices in enumerate(self.group_unique_indices):
                group_result = _finite_set_group(
                    unique_log_density[unique_indices],
                    unique_visible[unique_indices],
                    detection_probability,
                    clutter_rate,
                    self.alias_hz,
                    self.max_dp_cells,
                )
                log_likelihood[group_index] = group_result["log_likelihood"]
                unconditioned_log_likelihood[group_index] = group_result[
                    "unconditioned_log_likelihood"
                ]
                empty_probability[group_index] = group_result["empty_probability"]
                nonempty_probability[group_index] = group_result["nonempty_probability"]
                association[unique_indices] = group_result["association_probability"]
                clutter[unique_indices] = group_result["clutter_probability"]
                miss[group_index] = group_result["satellite_miss_probability"]
        else:
            group_cardinality = np.asarray(
                [len(indices) for indices in self.group_unique_indices], dtype=np.int64
            )
            for peak_count in np.unique(group_cardinality):
                cardinality_groups = np.flatnonzero(group_cardinality == peak_count)
                state_count = 1 << int(peak_count)
                cells_per_group = 2 * (satellite_count + 1) * state_count
                if cells_per_group > self.max_dp_cells:
                    raise ValueError(
                        f"finite-set DP requires {cells_per_group} cells, "
                        f"exceeding max_dp_cells={self.max_dp_cells}"
                    )
                batch_size = self.max_batch_dp_cells // cells_per_group
                if batch_size < 1:
                    raise ValueError(
                        f"one finite-set group requires {cells_per_group} cells, "
                        "exceeding max_batch_dp_cells="
                        f"{self.max_batch_dp_cells}"
                    )
                for start in range(0, len(cardinality_groups), batch_size):
                    batch_groups = cardinality_groups[start : start + batch_size]
                    batch_unique = np.stack(
                        [self.group_unique_indices[index] for index in batch_groups]
                    )
                    batch_result = _finite_set_group_batch(
                        unique_log_density[batch_unique],
                        unique_visible[batch_unique],
                        detection_probability,
                        clutter_rate,
                        self.alias_hz,
                        self.max_dp_cells,
                        self.max_batch_dp_cells,
                    )
                    log_likelihood[batch_groups] = batch_result["log_likelihood"]
                    unconditioned_log_likelihood[batch_groups] = batch_result[
                        "unconditioned_log_likelihood"
                    ]
                    empty_probability[batch_groups] = batch_result["empty_probability"]
                    nonempty_probability[batch_groups] = batch_result["nonempty_probability"]
                    association[batch_unique] = batch_result["association_probability"]
                    clutter[batch_unique] = batch_result["clutter_probability"]
                    miss[batch_groups] = batch_result["satellite_miss_probability"]

        row_association = (
            association[self.original_to_unique] * member_probability
            if satellite_count
            else np.empty((self.row_count, 0))
        )
        result = {
            "group_values": self.group_values.copy(),
            "log_likelihood": log_likelihood,
            "total_log_likelihood": float(np.sum(log_likelihood)),
            "unconditioned_log_likelihood": unconditioned_log_likelihood,
            "empty_probability": empty_probability,
            "nonempty_probability": nonempty_probability,
            "association_probability": association,
            "row_association_probability": row_association,
            "clutter_probability": clutter,
            "satellite_miss_probability": miss,
            "satellite_detection_probability": 1.0 - miss,
            "satellite_support": np.sum(association, axis=0),
            "expected_clutter_count": np.asarray(
                [np.sum(clutter[indices]) for indices in self.group_unique_indices]
            ),
            "original_to_unique": self.original_to_unique.copy(),
            "unique_group_index": self.unique_group_index.copy(),
            "raw_peak_count": np.asarray(
                [
                    sum(len(self.clusters[index]) for index in indices)
                    for indices in self.group_unique_indices
                ]
            ),
            "unique_peak_count": np.asarray(
                [len(indices) for indices in self.group_unique_indices]
            ),
            "sigma_hz": sigma_hz,
            "detection_probability": detection_probability.copy(),
            "clutter_rate": clutter_rate,
            "alias_hz": self.alias_hz,
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
            "dp_implementation": implementation,
        }
        if return_gradient:
            result["prediction_gradient"] = (
                row_association * row_log_gradient
                if satellite_count
                else np.empty((self.row_count, 0))
            )
        if return_precision:
            result["prediction_precision"] = row_association / sigma_hz**2
        return result


def prepare_finite_set_likelihood(
    measured,
    group,
    *,
    alias_hz=DEFAULT_ALIAS_HZ,
    max_peaks_per_group=DEFAULT_MAX_PEAKS_PER_GROUP,
    max_dp_cells=DEFAULT_MAX_DP_CELLS,
    max_batch_dp_cells=DEFAULT_MAX_BATCH_DP_CELLS,
):
    """Prepare immutable grouping and duplicate information for repeated calls."""

    return PreparedFiniteSetLikelihood(
        measured,
        group,
        alias_hz=alias_hz,
        max_peaks_per_group=max_peaks_per_group,
        max_dp_cells=max_dp_cells,
        max_batch_dp_cells=max_batch_dp_cells,
    )


def finite_set_likelihood(
    measured,
    predicted,
    visible,
    group,
    *,
    sigma_hz,
    detection_probability,
    clutter_rate,
    alias_hz=DEFAULT_ALIAS_HZ,
    max_peaks_per_group=DEFAULT_MAX_PEAKS_PER_GROUP,
    max_dp_cells=DEFAULT_MAX_DP_CELLS,
    max_batch_dp_cells=DEFAULT_MAX_BATCH_DP_CELLS,
    chunk_size=4096,
    implementation="batched",
    return_gradient=False,
    return_precision=False,
):
    """Prepare and evaluate a conditioned finite-set likelihood."""

    prepared = prepare_finite_set_likelihood(
        measured,
        group,
        alias_hz=alias_hz,
        max_peaks_per_group=max_peaks_per_group,
        max_dp_cells=max_dp_cells,
        max_batch_dp_cells=max_batch_dp_cells,
    )
    return prepared.evaluate(
        predicted,
        visible,
        sigma_hz=sigma_hz,
        detection_probability=detection_probability,
        clutter_rate=clutter_rate,
        chunk_size=chunk_size,
        implementation=implementation,
        return_gradient=return_gradient,
        return_precision=return_precision,
    )
