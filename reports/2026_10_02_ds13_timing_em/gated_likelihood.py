"""Normalized hard-gated Gaussian finite-set likelihood adapter."""

from __future__ import annotations

import math

import numpy as np
from finite_set_likelihood import (
    _detection_probabilities,
    _finite_set_group_batch,
    _logsumexp,
    circular_residual,
)


def gated_log_density_terms(residual, sigma_hz, gate_hz):
    """Return normalized gated log density and its prediction derivative."""

    residual = np.asarray(residual, dtype=float)
    if not np.ndim(sigma_hz) == 0 or not np.isfinite(sigma_hz) or sigma_hz <= 0:
        raise ValueError("sigma_hz must be a positive finite scalar")
    if not np.ndim(gate_hz) == 0 or not np.isfinite(gate_hz) or gate_hz <= 0:
        raise ValueError("gate_hz must be a positive finite scalar")
    sigma_hz = float(sigma_hz)
    gate_hz = float(gate_hz)
    normalization = (
        math.log(sigma_hz)
        + 0.5 * math.log(2 * math.pi)
        + math.log(math.erf(gate_hz / (math.sqrt(2) * sigma_hz)))
    )
    inside = np.isfinite(residual) & (np.abs(residual) <= gate_hz)
    log_density = np.where(
        inside,
        -0.5 * (residual / sigma_hz) ** 2 - normalization,
        -np.inf,
    )
    prediction_gradient = np.where(inside, residual / sigma_hz**2, 0.0)
    return log_density, prediction_gradient


def _validate_group_geometry(prepared, predicted, visible):
    for group_index, original_indices in enumerate(prepared.group_row_indices):
        group_visibility = visible[original_indices]
        if np.any(group_visibility != group_visibility[0]):
            raise ValueError(
                "visibility must be groupwise constant for finite-set "
                f"normalization; group {prepared.group_values[group_index]!r} conflicts"
            )
        group_visible = group_visibility[0]
        if not np.any(group_visible):
            continue
        reference = predicted[original_indices[0]]
        difference = circular_residual(
            predicted[original_indices], reference, prepared.alias_hz
        )
        tolerance = 8 * np.finfo(float).eps * np.maximum(
            np.maximum(np.abs(predicted[original_indices]), np.abs(reference)),
            prepared.alias_hz,
        )
        conflict = group_visible[None, :] & (np.abs(difference) > tolerance)
        if np.any(conflict):
            raise ValueError(
                "predicted means must be groupwise equal modulo alias for "
                f"finite-set normalization; group {prepared.group_values[group_index]!r} "
                "conflicts"
            )


class GatedLikelihood:
    """Finite-set likelihood with normalized hard-gated Gaussian signal edges."""

    def __init__(
        self,
        prepared,
        detection_probability,
        clutter_rate=2.0,
        *,
        gate_hz,
    ):
        if (
            not np.ndim(detection_probability) == 0
            or not np.isfinite(detection_probability)
            or not 0 <= detection_probability <= 1
        ):
            raise ValueError("detection_probability must be a finite scalar probability")
        if not np.isfinite(clutter_rate) or clutter_rate <= 0:
            raise ValueError("clutter_rate must be positive and finite")
        if (
            not np.ndim(gate_hz) == 0
            or not np.isfinite(gate_hz)
            or not 0 < gate_hz < prepared.alias_hz / 2
        ):
            raise ValueError("gate_hz must lie strictly between zero and half the alias")
        self.prepared = prepared
        self.detection_probability = float(detection_probability)
        self.clutter_rate = float(clutter_rate)
        self.gate_hz = float(gate_hz)
        self.last_result = None

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        satellite_weights=None,
        background_mass=None,
        return_gradient=False,
        return_precision=False,
    ):
        prepared = self.prepared
        predicted = np.asarray(predicted, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        if predicted.ndim != 2 or predicted.shape[0] != prepared.row_count:
            raise ValueError("predicted must have prepared rows by satellite columns")
        if visible.shape != predicted.shape or np.any(visible & ~np.isfinite(predicted)):
            raise ValueError("visibility and finite predictions must align")
        if not np.ndim(sigma_hz) == 0 or not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("sigma_hz must be a positive finite scalar")
        sigma_hz = float(sigma_hz)
        satellite_count = predicted.shape[1]
        if satellite_weights is not None and np.asarray(satellite_weights).shape != (
            satellite_count,
        ):
            raise ValueError("satellite_weights must align with predictions")
        _validate_group_geometry(prepared, predicted, visible)
        detection = _detection_probabilities(
            self.detection_probability, satellite_count
        )

        if satellite_count:
            residual = circular_residual(
                prepared.measured[:, None], predicted, prepared.alias_hz
            )
            row_log_density, row_log_gradient = gated_log_density_terms(
                residual, sigma_hz, self.gate_hz
            )
            row_log_density = np.where(visible, row_log_density, -np.inf)
            row_log_gradient = np.where(visible, row_log_gradient, 0.0)
        else:
            row_log_density = np.empty((prepared.row_count, 0))
            row_log_gradient = np.empty((prepared.row_count, 0))

        unique_log_density = np.full(
            (prepared.unique_peak_count, satellite_count), -np.inf
        )
        unique_visible = np.zeros_like(unique_log_density, dtype=bool)
        member_probability = np.zeros_like(row_log_density)
        for unique_index, members in enumerate(prepared.clusters):
            unique_visible[unique_index] = visible[members[0]]
            for satellite in range(satellite_count):
                log_values = row_log_density[members, satellite]
                log_total = _logsumexp(log_values)
                if not np.isfinite(log_total):
                    continue
                unique_log_density[unique_index, satellite] = (
                    log_total - np.log(len(members))
                )
                finite = np.isfinite(log_values)
                member_probability[members[finite], satellite] = np.exp(
                    log_values[finite] - log_total
                )

        group_count = len(prepared.group_values)
        log_likelihood = np.empty(group_count)
        unconditioned = np.empty(group_count)
        empty = np.empty(group_count)
        nonempty = np.empty(group_count)
        association = np.zeros_like(unique_log_density)
        clutter = np.zeros(prepared.unique_peak_count)
        miss = np.zeros((group_count, satellite_count))
        group_cardinality = np.asarray(
            [len(indices) for indices in prepared.group_unique_indices], dtype=np.int64
        )
        for peak_count in np.unique(group_cardinality):
            cardinality_groups = np.flatnonzero(group_cardinality == peak_count)
            state_count = 1 << int(peak_count)
            cells_per_group = 2 * (satellite_count + 1) * state_count
            if cells_per_group > prepared.max_dp_cells:
                raise ValueError(
                    f"finite-set DP requires {cells_per_group} cells, "
                    f"exceeding max_dp_cells={prepared.max_dp_cells}"
                )
            batch_size = prepared.max_batch_dp_cells // cells_per_group
            if batch_size < 1:
                raise ValueError(
                    f"one finite-set group requires {cells_per_group} cells, "
                    f"exceeding max_batch_dp_cells={prepared.max_batch_dp_cells}"
                )
            for start in range(0, len(cardinality_groups), batch_size):
                batch_groups = cardinality_groups[start : start + batch_size]
                batch_unique = np.stack(
                    [prepared.group_unique_indices[index] for index in batch_groups]
                )
                batch = _finite_set_group_batch(
                    unique_log_density[batch_unique],
                    unique_visible[batch_unique],
                    detection,
                    self.clutter_rate,
                    prepared.alias_hz,
                    prepared.max_dp_cells,
                    prepared.max_batch_dp_cells,
                )
                log_likelihood[batch_groups] = batch["log_likelihood"]
                unconditioned[batch_groups] = batch["unconditioned_log_likelihood"]
                empty[batch_groups] = batch["empty_probability"]
                nonempty[batch_groups] = batch["nonempty_probability"]
                association[batch_unique] = batch["association_probability"]
                clutter[batch_unique] = batch["clutter_probability"]
                miss[batch_groups] = batch["satellite_miss_probability"]

        row_association = association[prepared.original_to_unique] * member_probability
        expected_clutter = np.asarray(
            [np.sum(clutter[indices]) for indices in prepared.group_unique_indices]
        )
        result = {
            "group_values": prepared.group_values.copy(),
            "log_likelihood": log_likelihood,
            "total_log_likelihood": float(np.sum(log_likelihood)),
            "unconditioned_log_likelihood": unconditioned,
            "empty_probability": empty,
            "nonempty_probability": nonempty,
            "association_probability": association,
            "row_association_probability": row_association,
            "clutter_probability": clutter,
            "satellite_miss_probability": miss,
            "satellite_detection_probability": 1.0 - miss,
            "satellite_support": np.sum(association, axis=0),
            "expected_clutter_count": expected_clutter,
            "null_support": float(np.sum(expected_clutter)),
            "original_to_unique": prepared.original_to_unique.copy(),
            "unique_group_index": prepared.unique_group_index.copy(),
            "raw_peak_count": np.asarray(
                [
                    sum(len(prepared.clusters[index]) for index in indices)
                    for indices in prepared.group_unique_indices
                ]
            ),
            "unique_peak_count": group_cardinality,
            "sigma_hz": sigma_hz,
            "gate_hz": self.gate_hz,
            "detection_probability": detection,
            "clutter_rate": self.clutter_rate,
            "alias_hz": prepared.alias_hz,
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set_hard_gated_gaussian",
            "dp_implementation": "batched",
            "optimizer_satellite_weights_argument_ignored": (
                None
                if satellite_weights is None
                else np.asarray(satellite_weights, dtype=float).copy()
            ),
            "optimizer_background_mass_argument_ignored": (
                None if background_mass is None else float(background_mass)
            ),
        }
        if return_gradient:
            result["prediction_gradient"] = row_association * row_log_gradient
        if return_precision:
            result["prediction_precision"] = row_association / sigma_hz**2
            result["precision_semantics"] = (
                "complete-data Fisher away from hard gate boundaries"
            )
        self.last_result = result
        return result


__all__ = ["GatedLikelihood", "gated_log_density_terms"]
