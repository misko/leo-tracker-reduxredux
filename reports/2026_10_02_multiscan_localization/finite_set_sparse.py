"""Opt-in bounded-tail column packing for the frozen finite-set likelihood."""

from __future__ import annotations

import numpy as np
from finite_set_likelihood import _wrapped_normal_terms, circular_residual


class SparseFiniteSetLikelihoodAdapter:
    def __init__(self, prepared, detection_probability, clutter_rate=2.0, *, odds_cutoff=1e-16):
        if not 0 < detection_probability < 1 or not np.isfinite(detection_probability):
            raise ValueError("packing requires a common detection probability in (0, 1)")
        if not np.isfinite(clutter_rate) or clutter_rate <= 0:
            raise ValueError("clutter rate must be positive")
        if not np.isfinite(odds_cutoff) or odds_cutoff <= 0:
            raise ValueError("odds cutoff must be positive")
        self.prepared = prepared
        self.detection_probability = float(detection_probability)
        self.clutter_rate = float(clutter_rate)
        self.odds_cutoff = float(odds_cutoff)
        self.row_group = prepared.unique_group_index[prepared.original_to_unique]
        self.first_rows = np.asarray([rows[0] for rows in prepared.group_row_indices])
        self.last_result = None

    def evaluate(
        self, predicted, visible, *, sigma_hz, satellite_weights, background_mass,
        return_gradient=False, return_precision=False,
    ):
        predicted = np.asarray(predicted, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        prepared = self.prepared
        if predicted.ndim != 2 or predicted.shape[0] != prepared.row_count:
            raise ValueError("predictions must match prepared rows")
        if visible.shape != predicted.shape or np.any(visible & ~np.isfinite(predicted)):
            raise ValueError("visibility and finite predictions must align")
        if not np.ndim(sigma_hz) == 0 or not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("sigma must be positive and finite")
        satellite_count = predicted.shape[1]
        if np.asarray(satellite_weights).shape != (satellite_count,):
            raise ValueError("satellite weights must align")
        reference = predicted[self.first_rows][self.row_group]
        group_visible = visible[self.first_rows]
        if np.any(visible != group_visible[self.row_group]):
            raise ValueError("visibility must be groupwise constant")
        tolerance = 8 * np.finfo(float).eps * np.maximum(
            np.maximum(np.abs(predicted), np.abs(reference)), prepared.alias_hz,
        )
        difference = circular_residual(predicted, reference, prepared.alias_hz)
        if np.any(visible & (np.abs(difference) > tolerance)):
            raise ValueError("predictions must be groupwise equal modulo alias")
        residual = circular_residual(prepared.measured[:, None], predicted, prepared.alias_hz)
        density, _ = _wrapped_normal_terms(
            np.where(visible, residual, 0.0), float(sigma_hz), prepared.alias_hz, 4096, False,
        )
        probability = self.detection_probability
        log_odds = np.where(visible, density + np.log(probability / (1 - probability))
                            - np.log(self.clutter_rate / prepared.alias_hz), -np.inf)
        group_count = len(prepared.group_values)
        retained = np.zeros((group_count, satellite_count), dtype=bool)
        np.logical_or.at(retained, self.row_group, log_odds > np.log(self.odds_cutoff))
        counts = np.sum(retained, axis=1)
        packed_count = int(np.max(counts))
        columns = np.zeros((group_count, packed_count), dtype=int)
        packed_visible = np.zeros((group_count, packed_count), dtype=bool)
        group_indices, original_columns = np.nonzero(retained)
        packed_columns = (np.cumsum(retained, axis=1) - 1)[retained]
        columns[group_indices, packed_columns] = original_columns
        packed_visible[group_indices, packed_columns] = True
        row_columns = columns[self.row_group]
        packed_predicted = np.take_along_axis(predicted, row_columns, axis=1)
        packed = prepared.evaluate(
            packed_predicted, packed_visible[self.row_group], sigma_hz=sigma_hz,
            detection_probability=np.full(packed_count, probability),
            clutter_rate=self.clutter_rate, return_gradient=return_gradient,
            return_precision=return_precision,
        )
        missed_count = np.sum(group_visible & ~retained, axis=1)
        omitted_log_miss = missed_count * np.log1p(-probability)
        log_empty = -self.clutter_rate + np.sum(group_visible, axis=1) * np.log1p(-probability)
        nonempty = -np.expm1(log_empty)
        unconditioned = packed["unconditioned_log_likelihood"] + omitted_log_miss
        log_likelihood = unconditioned - np.log(nonempty)

        def scatter(values, groups):
            result = np.zeros((len(groups), satellite_count))
            rows, local_columns = np.nonzero(packed_visible[groups])
            result[rows, columns[groups[rows], local_columns]] = values[rows, local_columns]
            return result

        association = scatter(packed["association_probability"], prepared.unique_group_index)
        miss = np.ones((group_count, satellite_count))
        miss[group_indices, original_columns] = packed["satellite_miss_probability"][
            group_indices, packed_columns
        ]
        omitted_odds = np.where(retained[self.row_group], 0.0, np.exp(log_odds))
        error_bound = np.zeros(group_count)
        np.add.at(error_bound, self.row_group, np.sum(omitted_odds, axis=1))
        result = {
            **packed, "log_likelihood": log_likelihood,
            "total_log_likelihood": float(np.sum(log_likelihood)),
            "unconditioned_log_likelihood": unconditioned,
            "empty_probability": np.exp(log_empty), "nonempty_probability": nonempty,
            "association_probability": association,
            "row_association_probability": scatter(
                packed["row_association_probability"], self.row_group,
            ),
            "satellite_miss_probability": miss, "satellite_detection_probability": 1 - miss,
            "satellite_support": np.sum(association, axis=0),
            "detection_probability": np.full(satellite_count, probability),
            "null_support": float(np.sum(packed["expected_clutter_count"])),
            "optimizer_background_mass_argument_ignored": float(background_mass),
            "dp_implementation": "bounded_tail_packed_columns",
            "packed_satellite_count": packed_count,
            "retained_satellite_count_per_group": counts,
            "omitted_log_likelihood_upper_bound_per_group": error_bound,
            "total_omitted_log_likelihood_upper_bound": float(np.sum(error_bound)),
            "approximation": (
                "Omitted association edges replaced by misses; "
                "full nonempty normalization preserved."
            ),
        }
        if return_gradient:
            result["prediction_gradient"] = scatter(packed["prediction_gradient"], self.row_group)
        if return_precision:
            result["prediction_precision"] = scatter(packed["prediction_precision"], self.row_group)
        self.last_result = result
        return result
