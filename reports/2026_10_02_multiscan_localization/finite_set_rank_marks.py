"""Normalized discrete-rank marks for the frozen finite-set likelihood."""

from __future__ import annotations

import numpy as np
from finite_set_likelihood import (
    _detection_probabilities,
    _finite_set_group,
    _logsumexp,
    _wrapped_normal_terms,
    circular_residual,
)

RANK_COUNT = 8


def _probability_vector(values, name):
    values = np.asarray(values, dtype=float)
    if (
        values.shape != (RANK_COUNT,)
        or np.any(~np.isfinite(values))
        or np.any(values <= 0)
        or not np.isclose(np.sum(values), 1.0, rtol=0.0, atol=1e-12)
    ):
        raise ValueError(f"{name} must contain eight positive normalized probabilities")
    result = values.copy()
    result.setflags(write=False)
    return result


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


class RankMarkedFiniteSetLikelihoodAdapter:
    """Exact finite-set likelihood with one normalized discrete mark per unique peak."""

    def __init__(
        self,
        prepared,
        detection_probability,
        unique_ranks,
        q_signal,
        q_clutter,
        clutter_rate=2.0,
    ):
        if (
            not np.ndim(detection_probability) == 0
            or not np.isfinite(detection_probability)
            or not 0 <= detection_probability <= 1
        ):
            raise ValueError("detection_probability must be a finite scalar probability")
        if not np.isfinite(clutter_rate) or clutter_rate <= 0:
            raise ValueError("clutter_rate must be positive and finite")
        ranks = np.asarray(unique_ranks)
        if (
            ranks.shape != (prepared.unique_peak_count,)
            or not np.issubdtype(ranks.dtype, np.integer)
            or np.any(ranks < 0)
            or np.any(ranks >= RANK_COUNT)
        ):
            raise ValueError("unique_ranks must be integer ranks 0 through 7 per unique peak")
        self.prepared = prepared
        self.detection_probability = float(detection_probability)
        self.clutter_rate = float(clutter_rate)
        self.unique_ranks = ranks.astype(np.int64, copy=True)
        self.unique_ranks.setflags(write=False)
        self.q_signal = _probability_vector(q_signal, "q_signal")
        self.q_clutter = _probability_vector(q_clutter, "q_clutter")
        self._log_signal_to_clutter = np.log(
            self.q_signal[self.unique_ranks] / self.q_clutter[self.unique_ranks]
        )
        self._log_clutter_marks = np.log(self.q_clutter[self.unique_ranks])
        self.last_result = None

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        satellite_weights,
        background_mass,
        return_gradient=False,
        return_precision=False,
    ):
        prepared = self.prepared
        predicted = np.asarray(predicted, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        if predicted.ndim != 2 or predicted.shape[0] != prepared.row_count:
            raise ValueError("predictions must have prepared rows by satellite columns")
        if visible.shape != predicted.shape or np.any(visible & ~np.isfinite(predicted)):
            raise ValueError("visibility and finite predictions must align")
        if not np.ndim(sigma_hz) == 0 or not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("sigma_hz must be a positive finite scalar")
        satellite_count = predicted.shape[1]
        if np.asarray(satellite_weights).shape != (satellite_count,):
            raise ValueError("optimizer satellite weights do not match predictions")
        _validate_group_geometry(prepared, predicted, visible)

        detection = _detection_probabilities(
            self.detection_probability, satellite_count
        )
        if satellite_count:
            residual = circular_residual(prepared.measured[:, None], predicted, prepared.alias_hz)
            row_log_density, row_log_gradient = _wrapped_normal_terms(
                np.where(visible, residual, 0.0),
                float(sigma_hz),
                prepared.alias_hz,
                4096,
                return_gradient,
            )
            row_log_density = np.where(visible, row_log_density, -np.inf)
        else:
            row_log_density = np.empty((prepared.row_count, 0))
            row_log_gradient = (
                np.empty((prepared.row_count, 0)) if return_gradient else None
            )

        unique_log_density = np.full((prepared.unique_peak_count, satellite_count), -np.inf)
        unique_visible = np.zeros_like(unique_log_density, dtype=bool)
        member_probability = np.zeros_like(row_log_density)
        for unique_index, members in enumerate(prepared.clusters):
            for satellite in range(satellite_count):
                log_values = row_log_density[members, satellite]
                log_total = _logsumexp(log_values)
                if not np.isfinite(log_total):
                    continue
                unique_visible[unique_index, satellite] = True
                unique_log_density[unique_index, satellite] = (
                    log_total
                    - np.log(len(members))
                    + self._log_signal_to_clutter[unique_index]
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
        mark_constant = np.empty(group_count)
        for group_index, unique_indices in enumerate(prepared.group_unique_indices):
            group_result = _finite_set_group(
                unique_log_density[unique_indices],
                unique_visible[unique_indices],
                detection,
                self.clutter_rate,
                prepared.alias_hz,
                prepared.max_dp_cells,
            )
            mark_constant[group_index] = np.sum(self._log_clutter_marks[unique_indices])
            log_likelihood[group_index] = (
                group_result["log_likelihood"] + mark_constant[group_index]
            )
            unconditioned[group_index] = (
                group_result["unconditioned_log_likelihood"]
                + mark_constant[group_index]
            )
            empty[group_index] = group_result["empty_probability"]
            nonempty[group_index] = group_result["nonempty_probability"]
            association[unique_indices] = group_result["association_probability"]
            clutter[unique_indices] = group_result["clutter_probability"]
            miss[group_index] = group_result["satellite_miss_probability"]

        row_association = association[prepared.original_to_unique] * member_probability
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
            "expected_clutter_count": np.asarray(
                [np.sum(clutter[indices]) for indices in prepared.group_unique_indices]
            ),
            "original_to_unique": prepared.original_to_unique.copy(),
            "unique_group_index": prepared.unique_group_index.copy(),
            "raw_peak_count": np.asarray(
                [
                    sum(len(prepared.clusters[index]) for index in indices)
                    for indices in prepared.group_unique_indices
                ]
            ),
            "unique_peak_count": np.asarray(
                [len(indices) for indices in prepared.group_unique_indices]
            ),
            "sigma_hz": float(sigma_hz),
            "detection_probability": detection,
            "clutter_rate": self.clutter_rate,
            "alias_hz": prepared.alias_hz,
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set_with_normalized_discrete_rank_mark",
            "dp_implementation": "frozen_scalar_finite_set_group",
            "unique_ranks": self.unique_ranks.copy(),
            "q_signal": self.q_signal.copy(),
            "q_clutter": self.q_clutter.copy(),
            "group_log_clutter_mark_constant": mark_constant,
            "optimizer_background_mass_argument_ignored": float(background_mass),
            "adapter_null_support_semantics": "expected finite-set clutter peak count",
        }
        result["null_support"] = float(np.sum(result["expected_clutter_count"]))
        if return_gradient:
            result["prediction_gradient"] = row_association * row_log_gradient
        if return_precision:
            result["prediction_precision"] = row_association / float(sigma_hz) ** 2
            result["precision_semantics"] = "complete-data Fisher conditional on rank marks"
        self.last_result = result
        return result


__all__ = ["RANK_COUNT", "RankMarkedFiniteSetLikelihoodAdapter"]
