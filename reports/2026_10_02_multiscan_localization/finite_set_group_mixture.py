"""Normalized two-width finite-set likelihood with one noise state per group."""

from __future__ import annotations

import numpy as np


class GroupMixtureLikelihoodAdapter:
    def __init__(
        self, prepared, detection_probability, clutter_rate=2.0,
        *, narrow_sigma_hz=100.0, broad_sigma_hz=400.0, narrow_weight=0.8,
    ):
        if not 0 <= narrow_weight <= 1 or not np.isfinite(narrow_weight):
            raise ValueError("narrow weight must be a finite probability")
        if not 0 < narrow_sigma_hz <= broad_sigma_hz or not np.isfinite(broad_sigma_hz):
            raise ValueError("widths must be finite, positive, and ordered")
        self.prepared = prepared
        self.detection_probability = float(detection_probability)
        self.clutter_rate = float(clutter_rate)
        self.narrow_sigma_hz = float(narrow_sigma_hz)
        self.broad_sigma_hz = float(broad_sigma_hz)
        self.narrow_weight = float(narrow_weight)
        self.last_result = None

    def evaluate(
        self, predicted, visible, *, sigma_hz, satellite_weights, background_mass,
        return_gradient=False, return_precision=False,
    ):
        satellite_count = np.asarray(predicted).shape[1]
        if np.asarray(satellite_weights).shape != (satellite_count,):
            raise ValueError("optimizer satellite weights do not match predictions")
        options = dict(
            detection_probability=np.full(satellite_count, self.detection_probability),
            clutter_rate=self.clutter_rate, implementation="batched",
            return_gradient=return_gradient, return_precision=return_precision,
        )
        narrow = self.prepared.evaluate(
            predicted, visible, sigma_hz=self.narrow_sigma_hz, **options,
        )
        broad = self.prepared.evaluate(
            predicted, visible, sigma_hz=self.broad_sigma_hz, **options,
        )
        for name in ("empty_probability", "nonempty_probability"):
            if not np.array_equal(narrow[name], broad[name]):
                raise ValueError("width components must share nonempty conditioning")
        weight = self.narrow_weight
        if weight == 0:
            log_likelihood = broad["log_likelihood"].copy()
            narrow_posterior = np.zeros_like(log_likelihood)
        elif weight == 1:
            log_likelihood = narrow["log_likelihood"].copy()
            narrow_posterior = np.ones_like(log_likelihood)
        else:
            log_narrow = np.log(weight) + narrow["log_likelihood"]
            log_broad = np.log1p(-weight) + broad["log_likelihood"]
            log_likelihood = np.logaddexp(log_narrow, log_broad)
            narrow_posterior = np.exp(log_narrow - log_likelihood)
        unique_weights = narrow_posterior[narrow["unique_group_index"]]
        row_weights = unique_weights[narrow["original_to_unique"]]

        def mix(name, weights):
            left, right = narrow[name], broad[name]
            expanded = weights.reshape(weights.shape + (1,) * (left.ndim - 1))
            return expanded * left + (1 - expanded) * right

        result = {
            **narrow,
            "log_likelihood": log_likelihood,
            "total_log_likelihood": float(np.sum(log_likelihood)),
            "unconditioned_log_likelihood": (
                log_likelihood + np.log(narrow["nonempty_probability"])
            ),
            "association_probability": mix("association_probability", unique_weights),
            "row_association_probability": mix("row_association_probability", row_weights),
            "clutter_probability": mix("clutter_probability", unique_weights),
            "satellite_miss_probability": mix("satellite_miss_probability", narrow_posterior),
            "satellite_detection_probability": mix(
                "satellite_detection_probability", narrow_posterior,
            ),
            "expected_clutter_count": mix("expected_clutter_count", narrow_posterior),
            "sigma_hz": None,
            "group_narrow_posterior": narrow_posterior,
            "group_noise_model": "normalized conditional finite-set width mixture",
            "narrow_sigma_hz": self.narrow_sigma_hz,
            "broad_sigma_hz": self.broad_sigma_hz,
            "narrow_prior_probability": weight,
            "optimizer_sigma_hz_argument_ignored": float(sigma_hz),
            "optimizer_background_mass_argument_ignored": float(background_mass),
            "adapter_null_support_semantics": "expected finite-set clutter peak count",
        }
        result["satellite_support"] = np.sum(result["association_probability"], axis=0)
        result["null_support"] = float(np.sum(result["expected_clutter_count"]))
        if return_gradient:
            result["prediction_gradient"] = mix("prediction_gradient", row_weights)
        if return_precision:
            result["prediction_precision"] = mix("prediction_precision", row_weights)
            result["precision_semantics"] = "complete-data Fisher including latent group width"
        self.last_result = result
        return result
