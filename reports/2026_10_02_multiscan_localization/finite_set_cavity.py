"""Exact finite-set leave-one-satellite-out replacement scores."""

from __future__ import annotations

import numpy as np
from finite_set_likelihood import (
    _detection_probabilities,
    _logsumexp,
    _logsumexp_axis,
    _subset_indices,
    _wrapped_normal_terms,
    circular_residual,
)


def _group_rows(prepared):
    first_rows = np.asarray([rows[0] for rows in prepared.group_row_indices], dtype=np.int64)
    row_group = np.empty(prepared.row_count, dtype=np.int64)
    for group_index, rows in enumerate(prepared.group_row_indices):
        row_group[rows] = group_index
    return first_rows, row_group


def _validate_predictions(prepared, predicted, visible, first_rows=None, row_group=None):
    predicted = np.asarray(predicted, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    if predicted.ndim != 2 or predicted.shape[0] != prepared.row_count:
        raise ValueError("predicted must have prepared rows by satellite columns")
    if visible.shape != predicted.shape:
        raise ValueError("visible must match predicted")
    if np.any(visible & ~np.isfinite(predicted)):
        raise ValueError("visible predictions must be finite")
    if first_rows is None or row_group is None:
        first_rows, row_group = _group_rows(prepared)
    reference_visible = visible[first_rows][row_group]
    visibility_conflict = visible != reference_visible
    if np.any(visibility_conflict):
        row = int(np.flatnonzero(np.any(visibility_conflict, axis=1))[0])
        raise ValueError(
            "visibility must be groupwise constant for finite-set normalization; "
            f"group {prepared.group_values[row_group[row]]!r} conflicts"
        )
    reference = predicted[first_rows][row_group]
    difference = circular_residual(predicted, reference, prepared.alias_hz)
    tolerance = (
        8
        * np.finfo(float).eps
        * np.maximum(np.maximum(np.abs(predicted), np.abs(reference)), prepared.alias_hz)
    )
    conflict = reference_visible & (np.abs(difference) > tolerance)
    if np.any(conflict):
        row = int(np.flatnonzero(np.any(conflict, axis=1))[0])
        raise ValueError(
            "predicted means must be groupwise equal modulo alias for finite-set "
            f"normalization; group {prepared.group_values[row_group[row]]!r} conflicts"
        )
    return predicted, visible


def _unique_log_density(prepared, predicted, visible, sigma_hz, chunk_size):
    satellite_count = predicted.shape[1]
    if satellite_count == 0:
        return (
            np.empty((prepared.unique_peak_count, 0)),
            np.empty((prepared.unique_peak_count, 0), dtype=bool),
        )
    residual = circular_residual(prepared.measured[:, None], predicted, prepared.alias_hz)
    residual = np.where(visible, residual, 0.0)
    row_log_density, _ = _wrapped_normal_terms(
        residual,
        sigma_hz,
        prepared.alias_hz,
        chunk_size,
        False,
    )
    row_log_density = np.where(visible, row_log_density, -np.inf)
    unique_log_density = np.full((prepared.unique_peak_count, satellite_count), -np.inf)
    unique_visible = np.zeros_like(unique_log_density, dtype=bool)
    singleton_unique = np.asarray(
        [index for index, members in enumerate(prepared.clusters) if len(members) == 1],
        dtype=np.int64,
    )
    singleton_rows = np.asarray(
        [prepared.clusters[index][0] for index in singleton_unique], dtype=np.int64
    )
    unique_log_density[singleton_unique] = row_log_density[singleton_rows]
    unique_visible[singleton_unique] = visible[singleton_rows]
    for unique_index, members in enumerate(prepared.clusters):
        if len(members) == 1:
            continue
        for satellite in range(satellite_count):
            log_total = _logsumexp(row_log_density[members, satellite])
            if not np.isfinite(log_total):
                continue
            unique_visible[unique_index, satellite] = True
            unique_log_density[unique_index, satellite] = log_total - np.log(len(members))
    return unique_log_density, unique_visible


def _cavity_group_partitions(
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
            f"finite-set cavity DP requires {required_cells} cells, "
            f"exceeding max_dp_cells={max_dp_cells}"
        )
    masks, without_peak, with_peak = _subset_indices(peak_count)
    cardinality = np.fromiter(
        (int(mask).bit_count() for mask in masks),
        dtype=np.int64,
        count=state_count,
    )
    group_visible = np.any(visible, axis=0)
    effective_detection = np.where(group_visible, detection_probability, 0.0)
    with np.errstate(divide="ignore"):
        log_detection = np.log(effective_detection)
        log_miss = np.log1p(-effective_detection)
    forward = np.full(state_count, -np.inf)
    forward[0] = 0.0
    for satellite in range(satellite_count):
        next_row = forward + log_miss[satellite]
        if np.isfinite(log_detection[satellite]):
            for peak in np.flatnonzero(visible[:, satellite]):
                source = without_peak[peak]
                target = with_peak[peak]
                candidate = forward[source] + log_detection[satellite]
                candidate = candidate + log_density[peak, satellite]
                next_row[target] = np.logaddexp(next_row[target], candidate)
        forward = next_row

    clutter_count = peak_count - cardinality
    log_tail = -clutter_rate + clutter_count * np.log(clutter_rate)
    log_tail = log_tail - clutter_count * np.log(alias_hz)
    log_full = _logsumexp(forward + log_tail)
    log_without_peak = np.empty(peak_count)
    for peak in range(peak_count):
        source = without_peak[peak]
        removed_clutter_count = peak_count - 1 - cardinality[source]
        removed_log_tail = (
            -clutter_rate
            + removed_clutter_count * np.log(clutter_rate)
            - removed_clutter_count * np.log(alias_hz)
        )
        log_without_peak[peak] = _logsumexp(forward[source] + removed_log_tail)
    log_empty = -clutter_rate + float(np.sum(log_miss))
    if not np.isfinite(log_full):
        raise FloatingPointError("finite-set cavity has zero observed-set probability")
    if log_empty >= 0:
        raise FloatingPointError("finite-set cavity has zero nonempty probability")
    return log_full, log_without_peak, log_empty


class FiniteSetCavityScorer:
    def __init__(
        self,
        prepared,
        predicted,
        visible,
        satellite_column,
        sigma_hz,
        detection_probability,
        clutter_rate,
        *,
        chunk_size=4096,
    ):
        self.prepared = prepared
        self.first_rows, self.row_group = _group_rows(prepared)
        predicted, visible = _validate_predictions(
            prepared,
            predicted,
            visible,
            self.first_rows,
            self.row_group,
        )
        satellite_count = predicted.shape[1]
        if not isinstance(satellite_column, (int, np.integer)) or not (
            0 <= satellite_column < satellite_count
        ):
            raise ValueError("satellite_column is outside the prediction columns")
        if not np.isfinite(clutter_rate) or clutter_rate <= 0:
            raise ValueError("clutter_rate must be positive and finite")
        if not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("sigma_hz must be positive and finite")
        if not isinstance(chunk_size, (int, np.integer)) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        probabilities = _detection_probabilities(detection_probability, satellite_count)
        keep = np.arange(satellite_count) != satellite_column
        unique_log_density, unique_visible = _unique_log_density(
            prepared,
            predicted[:, keep],
            visible[:, keep],
            float(sigma_hz),
            int(chunk_size),
        )
        group_count = len(prepared.group_values)
        log_cavity_full = np.empty(group_count)
        log_cavity_without_peak = []
        log_cavity_empty = np.empty(group_count)
        for group_index, unique_indices in enumerate(prepared.group_unique_indices):
            full, without_peak, empty = _cavity_group_partitions(
                unique_log_density[unique_indices],
                unique_visible[unique_indices],
                probabilities[keep],
                float(clutter_rate),
                prepared.alias_hz,
                prepared.max_dp_cells,
            )
            log_cavity_full[group_index] = full
            log_cavity_without_peak.append(without_peak)
            log_cavity_empty[group_index] = empty
        self.satellite_column = int(satellite_column)
        self.satellite_index = self.satellite_column
        self.detection_probability = float(probabilities[satellite_column])
        self.clutter_rate = float(clutter_rate)
        self.sigma_hz = float(sigma_hz)
        self.chunk_size = int(chunk_size)
        self.log_cavity_full = log_cavity_full
        self.log_cavity_without_peak = tuple(log_cavity_without_peak)
        self.log_cavity_empty = log_cavity_empty
        cardinality = np.asarray(
            [len(indices) for indices in prepared.group_unique_indices], dtype=np.int64
        )
        batches = []
        for peak_count in np.unique(cardinality):
            groups = np.flatnonzero(cardinality == peak_count)
            unique_indices = np.stack([prepared.group_unique_indices[index] for index in groups])
            without_peak = np.stack([log_cavity_without_peak[index] for index in groups])
            batches.append((groups, unique_indices, without_peak))
        self.cardinality_batches = tuple(batches)
        for value in (
            self.first_rows,
            self.row_group,
            self.log_cavity_full,
            self.log_cavity_empty,
            *self.log_cavity_without_peak,
        ):
            value.setflags(write=False)

    def evaluate(self, predicted, visible):
        predicted = np.asarray(predicted, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        if predicted.shape == (self.prepared.row_count,):
            predicted = predicted[:, None]
        if visible.shape == (self.prepared.row_count,):
            visible = visible[:, None]
        if predicted.shape != (self.prepared.row_count, 1):
            raise ValueError("replacement prediction must contain one value per prepared row")
        if visible.shape != predicted.shape:
            raise ValueError("replacement visibility must match prediction")
        predicted, visible = _validate_predictions(
            self.prepared,
            predicted,
            visible,
            self.first_rows,
            self.row_group,
        )
        unique_log_density, _ = _unique_log_density(
            self.prepared,
            predicted,
            visible,
            self.sigma_hz,
            self.chunk_size,
        )
        group_count = len(self.prepared.group_values)
        log_likelihood = np.empty(group_count)
        unconditioned = np.empty(group_count)
        empty_probability = np.empty(group_count)
        nonempty_probability = np.empty(group_count)
        probability = self.detection_probability
        with np.errstate(divide="ignore"):
            log_detection = float(np.log(probability))
            log_miss = float(np.log1p(-probability))
        group_visible = visible[self.first_rows, 0]
        for groups, unique_indices, without_peak in self.cardinality_batches:
            visible_batch = group_visible[groups]
            missed = np.where(
                visible_batch,
                self.log_cavity_full[groups] + log_miss,
                self.log_cavity_full[groups],
            )
            detected = log_detection + unique_log_density[unique_indices, 0] + without_peak
            detected = np.where(visible_batch[:, None], detected, -np.inf)
            terms = np.concatenate((missed[:, None], detected), axis=1)
            batch_unconditioned = _logsumexp_axis(terms, axis=1)
            batch_log_empty = np.where(
                visible_batch,
                self.log_cavity_empty[groups] + log_miss,
                self.log_cavity_empty[groups],
            )
            unconditioned[groups] = batch_unconditioned
            empty_probability[groups] = np.exp(batch_log_empty)
            nonempty_probability[groups] = -np.expm1(batch_log_empty)
            log_likelihood[groups] = batch_unconditioned - np.log(nonempty_probability[groups])
        if np.any(~np.isfinite(unconditioned)):
            group_index = int(np.flatnonzero(~np.isfinite(unconditioned))[0])
            raise FloatingPointError(
                f"replacement gives group {self.prepared.group_values[group_index]!r} "
                "zero observed-set probability"
            )
        if np.any(nonempty_probability <= 0):
            group_index = int(np.flatnonzero(nonempty_probability <= 0)[0])
            raise FloatingPointError(
                f"replacement gives group {self.prepared.group_values[group_index]!r} "
                "zero nonempty probability"
            )
        return {
            "group_values": self.prepared.group_values.copy(),
            "group_log_likelihood": log_likelihood,
            "log_likelihood": log_likelihood,
            "total_log_likelihood": float(np.sum(log_likelihood)),
            "unconditioned_log_likelihood": unconditioned,
            "empty_probability": empty_probability,
            "nonempty_probability": nonempty_probability,
            "satellite_column": self.satellite_column,
            "satellite_index": self.satellite_column,
            "detection_probability": probability,
            "clutter_rate": self.clutter_rate,
            "sigma_hz": self.sigma_hz,
            "alias_hz": self.prepared.alias_hz,
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
            "replacement_exact": True,
        }


def prepare_replacement_scorer(
    prepared,
    predicted,
    visible,
    satellite_column=None,
    sigma_hz=None,
    detection_probability=None,
    clutter_rate=None,
    *,
    satellite_index=None,
    chunk_size=4096,
):
    if satellite_column is not None and satellite_index is not None:
        raise ValueError("supply satellite_column or satellite_index, not both")
    column = satellite_index if satellite_column is None else satellite_column
    return FiniteSetCavityScorer(
        prepared,
        predicted,
        visible,
        column,
        sigma_hz,
        detection_probability,
        clutter_rate,
        chunk_size=chunk_size,
    )


FiniteSetReplacementScorer = FiniteSetCavityScorer


__all__ = [
    "FiniteSetCavityScorer",
    "FiniteSetReplacementScorer",
    "prepare_replacement_scorer",
]
