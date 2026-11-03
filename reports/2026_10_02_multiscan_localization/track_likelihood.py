"""Whole-track identity likelihood with disjoint raw-group accounting.

Each anchor has one latent satellite identity shared by all of its source
groups.  A frozen per-group contamination probability permits null events
within a satellite track without allowing the satellite identity to switch.
Groups outside anchors retain the independent satellite mixture.  Every
source group belongs to exactly one of those two paths.

As with ``grouped_likelihood``, this is a likelihood proxy rather than a
calibrated posterior because stored GLRT alternatives and neighboring source
groups can be correlated.
"""

from __future__ import annotations

import numpy as np
from grouped_likelihood import (
    DEFAULT_ALIAS_HZ,
    _logsumexp,
    _sigma_columns,
    _wrapped_normal_terms,
    circular_residual,
)


def _as_key(value):
    return value.item() if isinstance(value, np.generic) else value


def _log_weights(values):
    with np.errstate(divide="ignore"):
        return np.where(values > 0, np.log(values), -np.inf)


def _validate_probability_mass(values, expected_shape, name):
    values = np.asarray(values, dtype=float)
    if values.shape != expected_shape:
        raise ValueError(f"{name} must have shape {expected_shape}")
    if np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError(f"{name} must be finite and non-negative")
    return values


class PreparedTrackGroupedLikelihood:
    """Frozen row alternatives and a disjoint source-group anchor partition."""

    def __init__(self, measured, group, row_weights, anchors, alias_hz):
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
        group_owners = np.repeat(np.arange(len(groups)), group_counts)
        sorted_weights = row_weights[order]
        group_weight = np.add.reduceat(sorted_weights, group_starts)
        if np.any(group_weight <= 0):
            bad = int(np.flatnonzero(group_weight <= 0)[0])
            raise ValueError(f"row_weights have zero mass in group {groups[bad]!r}")
        normalized_weights = sorted_weights / group_weight[group_owners]

        group_lookup = {_as_key(value): index for index, value in enumerate(groups)}
        group_owner_anchor = np.full(len(groups), -1, dtype=int)
        anchor_group_indices = []
        anchor_group_values = []
        for anchor_index, anchor in enumerate(anchors):
            values = np.asarray(anchor)
            if values.ndim != 1 or len(values) == 0:
                raise ValueError("each anchor must be a nonempty one-dimensional array")
            keys = [_as_key(value) for value in values]
            if len(set(keys)) != len(keys):
                raise ValueError("an anchor contains duplicate source groups")
            try:
                indices = np.asarray([group_lookup[key] for key in keys], dtype=int)
            except KeyError as error:
                raise ValueError(
                    f"anchor contains unknown source group {error.args[0]!r}"
                ) from error
            duplicate = group_owner_anchor[indices] >= 0
            if np.any(duplicate):
                value = groups[indices[np.flatnonzero(duplicate)[0]]]
                raise ValueError(f"source group {value!r} belongs to multiple anchors")
            group_owner_anchor[indices] = anchor_index
            anchor_group_indices.append(indices)
            anchor_group_values.append(groups[indices].copy())

        with np.errstate(divide="ignore"):
            log_row_weights = np.where(normalized_weights > 0, np.log(normalized_weights), -np.inf)
        self.measured = measured[order].copy()
        self.group_values = groups.copy()
        self.order = order
        self.group_starts = group_starts
        self.group_counts = group_counts
        self.group_owners = group_owners
        self.log_row_weights = log_row_weights
        self.group_owner_anchor = group_owner_anchor
        self.anchor_group_indices = tuple(anchor_group_indices)
        self.anchor_group_values = tuple(anchor_group_values)
        self.raw_group_indices = np.flatnonzero(group_owner_anchor < 0)
        self.alias_hz = float(alias_hz)
        for value in (
            self.measured,
            self.group_values,
            self.order,
            self.group_starts,
            self.group_counts,
            self.group_owners,
            self.log_row_weights,
            self.group_owner_anchor,
            self.raw_group_indices,
            *self.anchor_group_indices,
            *self.anchor_group_values,
        ):
            value.setflags(write=False)

    @property
    def row_count(self):
        return len(self.measured)

    @property
    def anchor_count(self):
        return len(self.anchor_group_indices)

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        raw_satellite_mass,
        raw_background_mass,
        anchor_satellite_mass,
        anchor_unknown_mass,
        track_contamination=0.2,
        return_gradient=False,
        return_precision=False,
    ):
        """Evaluate the partitioned likelihood and optional prediction gradient."""

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
        satellite_count = predicted.shape[1]
        sigma_hz, scalar_sigma = _sigma_columns(sigma_hz, satellite_count)
        raw_satellite_mass = _validate_probability_mass(
            raw_satellite_mass, (satellite_count,), "raw_satellite_mass"
        )
        if not np.isfinite(raw_background_mass) or not 0 < raw_background_mass <= 1:
            raise ValueError("raw_background_mass must lie in (0, 1]")
        if not np.isclose(
            raw_background_mass + np.sum(raw_satellite_mass), 1.0, rtol=0, atol=1e-12
        ):
            raise ValueError("raw background and satellite masses must sum to one")

        anchor_satellite_mass = np.asarray(anchor_satellite_mass, dtype=float)
        if self.anchor_count == 0 and anchor_satellite_mass.size == 0:
            anchor_satellite_mass = np.empty((0, satellite_count))
        anchor_satellite_mass = _validate_probability_mass(
            anchor_satellite_mass,
            (self.anchor_count, satellite_count),
            "anchor_satellite_mass",
        )
        anchor_unknown_mass = _validate_probability_mass(
            anchor_unknown_mass, (self.anchor_count,), "anchor_unknown_mass"
        )
        if self.anchor_count and not np.allclose(
            anchor_unknown_mass + np.sum(anchor_satellite_mass, axis=1),
            1.0,
            rtol=0,
            atol=1e-12,
        ):
            raise ValueError("each anchor's unknown and satellite masses must sum to one")
        contamination = np.asarray(track_contamination, dtype=float)
        if contamination.ndim == 0:
            contamination = np.full(self.anchor_count, float(contamination))
        if contamination.shape != (self.anchor_count,):
            raise ValueError("track_contamination must be scalar or have one value per anchor")
        if (
            np.any(~np.isfinite(contamination))
            or np.any(contamination <= 0)
            or np.any(contamination > 1)
        ):
            raise ValueError("track_contamination must lie in (0, 1]")

        ordered_prediction = predicted[self.order]
        ordered_visible = visible[self.order]
        residual = circular_residual(self.measured[:, None], ordered_prediction, self.alias_hz)
        residual = np.where(ordered_visible, residual, 0.0)
        log_density, log_density_prediction_gradient = _wrapped_normal_terms(
            residual,
            sigma_hz,
            self.alias_hz,
            4096,
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

        log_uniform = -np.log(self.alias_hz)
        group_signal_responsibility = np.zeros_like(group_log_signal)
        raw_log_likelihood = np.empty(len(self.raw_group_indices))
        if len(self.raw_group_indices):
            raw_signal_components = (
                _log_weights(raw_satellite_mass)[None, :] + group_log_signal[self.raw_group_indices]
            )
            raw_null_component = np.full(
                len(self.raw_group_indices), np.log(raw_background_mass) + log_uniform
            )
            raw_log_likelihood = np.logaddexp(
                raw_null_component,
                _logsumexp(raw_signal_components, axis=1),
            )
            group_signal_responsibility[self.raw_group_indices] = np.exp(
                raw_signal_components - raw_log_likelihood[:, None]
            )

        track_log_likelihood = np.empty(self.anchor_count)
        track_identity_responsibility = np.zeros_like(anchor_satellite_mass)
        track_unknown_responsibility = np.zeros(self.anchor_count)
        for anchor_index, indices in enumerate(self.anchor_group_indices):
            epsilon = contamination[anchor_index]
            log_contamination = np.log(epsilon) + log_uniform
            log_detection = (-np.inf if epsilon == 1 else np.log1p(-epsilon)) + group_log_signal[
                indices
            ]
            log_conditional = np.logaddexp(log_contamination, log_detection)
            candidate_components = _log_weights(anchor_satellite_mass[anchor_index]) + np.sum(
                log_conditional, axis=0
            )
            unknown_component = (
                _log_weights(np.asarray(anchor_unknown_mass[anchor_index]))
                + len(indices) * log_uniform
            )
            track_log_likelihood[anchor_index] = np.logaddexp(
                unknown_component, _logsumexp(candidate_components)
            )
            track_identity_responsibility[anchor_index] = np.exp(
                candidate_components - track_log_likelihood[anchor_index]
            )
            track_unknown_responsibility[anchor_index] = np.exp(
                unknown_component - track_log_likelihood[anchor_index]
            )
            detection_responsibility = np.exp(log_detection - log_conditional)
            group_signal_responsibility[indices] = (
                track_identity_responsibility[anchor_index][None, :] * detection_responsibility
            )

        satellite_support = np.sum(group_signal_responsibility, axis=0)
        group_null_responsibility = 1.0 - np.sum(group_signal_responsibility, axis=1)
        null_support = float(np.sum(group_null_responsibility))
        total_log_likelihood = float(np.sum(raw_log_likelihood) + np.sum(track_log_likelihood))
        baseline_log_likelihood = float(len(self.group_values) * log_uniform)
        result = {
            "group_values": self.group_values.copy(),
            "total_log_likelihood": total_log_likelihood,
            "satellite_support": satellite_support,
            "null_support": null_support,
            "group_satellite_responsibility": group_signal_responsibility,
            "group_null_responsibility": group_null_responsibility,
            "track_identity_responsibility": track_identity_responsibility,
            "track_unknown_responsibility": track_unknown_responsibility,
            "track_null_responsibility": track_unknown_responsibility.copy(),
            "raw_group_values": self.group_values[self.raw_group_indices].copy(),
            "anchor_group_values": tuple(values.copy() for values in self.anchor_group_values),
            "raw_group_log_likelihood": raw_log_likelihood,
            "track_log_likelihood": track_log_likelihood,
            "raw_group_log_bayes_factor": raw_log_likelihood - log_uniform,
            "track_log_bayes_factor": track_log_likelihood
            - np.asarray([len(indices) for indices in self.anchor_group_indices]) * log_uniform,
            "baseline_log_likelihood": baseline_log_likelihood,
            "log_evidence_ratio": total_log_likelihood - baseline_log_likelihood,
            "group_count": len(self.group_values),
            "anchor_count": self.anchor_count,
            "alternative_count": self.group_counts.copy(),
            "alias_hz": self.alias_hz,
            "sigma_hz": float(sigma_hz) if scalar_sigma else sigma_hz.copy(),
        }

        if return_gradient or return_precision:
            row_group_log_signal = group_log_signal[self.group_owners]
            row_signal_responsibility = np.zeros_like(weighted)
            usable = ordered_visible & np.isfinite(row_group_log_signal)
            row_signal_responsibility[usable] = np.exp(
                weighted[usable] - row_group_log_signal[usable]
            )
            ordered_signal_mass = (
                group_signal_responsibility[self.group_owners] * row_signal_responsibility
            )
            if return_gradient:
                ordered_gradient = ordered_signal_mass * log_density_prediction_gradient
                prediction_gradient = np.empty_like(ordered_gradient)
                prediction_gradient[self.order] = ordered_gradient
                result["prediction_gradient"] = prediction_gradient
            if return_precision:
                precision = np.empty_like(ordered_signal_mass)
                sigma_squared = sigma_hz**2 if scalar_sigma else sigma_hz[None, :] ** 2
                precision[self.order] = ordered_signal_mass / sigma_squared
                result["prediction_precision"] = precision
        return result


def prepare_track_grouped_likelihood(
    measured,
    group,
    *,
    row_weights,
    anchors,
    alias_hz=DEFAULT_ALIAS_HZ,
):
    """Freeze row masses and disjoint anchors expressed as source-group values."""

    return PreparedTrackGroupedLikelihood(measured, group, row_weights, anchors, alias_hz)


__all__ = ["PreparedTrackGroupedLikelihood", "prepare_track_grouped_likelihood"]
