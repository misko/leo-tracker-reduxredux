"""Fixed-frequency geographic scoring with one shared detection effect/track."""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np

import paired_reception_evaluator as paired
from detection_random_intercept_refined import candidate_detection_loglik
from robust_core import train_shortlist, joint_heldout_score


runner = paired.runner


def _logsumexp(values):
    values = np.asarray(values, float); maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def shared_joint_heldout_score(predicted_hz, candidate_east, measured_hz,
                               train_mask, shortlist, reception_rows, *,
                               ratio_variance, detection_sigma,
                               fit_order=64, verify_order=128,
                               quadrature_tolerance=.001):
    """Replace only candidate detection LL with a shared-effect integral."""
    base = joint_heldout_score(
        predicted_hz, candidate_east, measured_hz, train_mask, shortlist,
        reception_rows, ratio_variance=ratio_variance)
    sigma = float(detection_sigma)
    if not math.isfinite(sigma) or sigma < 0:
        raise ValueError("detection_sigma must be finite and nonnegative")
    if (not math.isfinite(quadrature_tolerance) or quadrature_tolerance < 0 or
            not isinstance(fit_order, int) or not isinstance(verify_order, int)):
        raise ValueError("invalid quadrature configuration")
    predicted = np.asarray(predicted_hz, float)
    east = np.asarray(candidate_east, float)
    measured = np.asarray(measured_hz, float)
    training = np.asarray(train_mask, bool)
    indices = np.asarray(shortlist["candidate_indices"], int)
    log_weights = np.asarray(shortlist["log_weights"], float)
    frequency = np.asarray(base["candidate_frequency_log_likelihood"], float)
    ratio = np.asarray(base["candidate_ratio_log_likelihood"], float)
    logits = []; reverse_logits = []; outcomes = []
    reverse_ratio = np.zeros(len(indices)); reconstructed_ratio = np.zeros(len(indices))
    normal_constant = -.5 * math.log(2. * math.pi * float(ratio_variance))
    for row in reception_rows:
        observation = int(row["observation_index"])
        x = east[indices, observation]
        intercept = float(row["detection_logit_east0"])
        slope = float(row["detection_east_slope"])
        logits.append(intercept + slope * x)
        reverse_logits.append(intercept - slope * x)
        outcomes.append(bool(row["matched"]))
        if row["matched"]:
            observed = float(row["log_margin_ratio_rx1_rx0"])
            mean = float(row["ratio_mean_east0"])
            ratio_slope = float(row["ratio_east_slope"])
            reconstructed_ratio += normal_constant - .5 * (
                observed - (mean + ratio_slope * x))**2 / ratio_variance
            reverse_ratio += normal_constant - .5 * (
                observed - (mean - ratio_slope * x))**2 / ratio_variance
    if not np.allclose(ratio, reconstructed_ratio, rtol=0, atol=1e-12):
        raise ValueError("ratio reconstruction changed frozen likelihood")
    if outcomes:
        normal_matrix = np.asarray(logits, float).T
        reverse_matrix = np.asarray(reverse_logits, float).T
        fitted = candidate_detection_loglik(
            normal_matrix, outcomes, sigma, fit_order)
        reverse_fitted = candidate_detection_loglik(
            reverse_matrix, outcomes, sigma, fit_order)
        verified = candidate_detection_loglik(
            normal_matrix, outcomes, sigma, verify_order)
        reverse_verified = candidate_detection_loglik(
            reverse_matrix, outcomes, sigma, verify_order)
        maximum = float(max(np.max(np.abs(fitted - verified)),
                            np.max(np.abs(reverse_fitted - reverse_verified))))
    else:
        fitted = reverse_fitted = np.zeros(len(indices)); maximum = 0.
    if maximum > quadrature_tolerance:
        raise FloatingPointError("shared-effect quadrature verification failed")
    reserve_count = int(np.count_nonzero(~training))
    def score(extra):
        return float(-_logsumexp(log_weights + frequency + extra) / reserve_count)
    scores = {
        "D": score(np.zeros(len(indices))),
        "D_plus_detection": score(fitted),
        "D_plus_geometry": score(fitted + ratio),
        "D_plus_reversed_geometry": score(reverse_fitted + reverse_ratio),
    }
    result = dict(base)
    result.update({
        "scores": scores,
        "candidate_detection_log_likelihood": fitted.tolist(),
        "candidate_reversed_detection_log_likelihood": reverse_fitted.tolist(),
        "candidate_reversed_ratio_log_likelihood": reverse_ratio.tolist(),
        "detection_sigma": sigma,
        "quadrature": {"fit_order": fit_order, "verification_order": verify_order,
                       "maximum_candidate_loglik_absolute_difference": maximum,
                       "tolerance": quadrature_tolerance, "passed": True},
    })
    return result


def score_variants(predictions, east, measured, training, shortlist, variants):
    values = {name: shared_joint_heldout_score(
        predictions, east, measured, training, shortlist, rows,
        ratio_variance=variance, detection_sigma=sigma)
              for name, (rows, variance, sigma) in variants.items()}
    d = [row["scores"]["D"] for row in values.values()]
    if not d or not np.allclose(d, d[0], rtol=0, atol=1e-12):
        raise ValueError("reception variants changed frequency score")
    return values


class SharedEffectEvaluator(paired.PairedEvaluator):
    """Paired geographic evaluator with optional shared-effect variants."""

    def __init__(self, banks, origin, variants, parameters):
        compatibility = {name: (rows, variance)
                         for name, (rows, variance, _sigma) in variants.items()}
        super().__init__(banks, origin, compatibility, parameters)
        self.variants = variants

    def evaluate(self, east, north):
        key = (float(east), float(north))
        if key in self.cache: return self.cache[key]
        lat, lon = runner.base.coordinates(*self.origin, *key)
        receiver = runner.base.point(lat, lon).ecef_km
        east_axis = np.array([-np.sin(np.deg2rad(lon)), np.cos(np.deg2rad(lon)), 0.])
        blocks = defaultdict(list)
        for block in self.predictions(*key): blocks[block.track_id].append(block)
        totals = {name: defaultdict(float) for name in self.variants}
        maxima = {name: 0. for name in self.variants}; weight_sum = 0
        for tid, bank in self.banks.items():
            track = bank.source; chunks = blocks[tid]
            predictions = np.concatenate([b.predictions_hz[:, 0, :] for b in chunks])
            ids = np.concatenate([b.candidate_ids for b in chunks])
            visible = np.concatenate([b.visible for b in chunks])
            shortlist = train_shortlist(
                predictions, track.measured_hz, track.training_mask, visible,
                scale_hz=self.parameters["scale_hz"],
                df=self.parameters["degrees_of_freedom"])
            indices = np.asarray(shortlist["candidate_indices"]); chosen = ids[indices]
            short = dict(shortlist, candidate_indices=list(range(len(indices))))
            positions = bank.position_km[
                [self.index[tid][int(candidate)] for candidate in chosen], 0, :, :]
            direction = ((positions - receiver) /
                         np.linalg.norm(positions - receiver, axis=-1, keepdims=True))
            variants = {name: (rows[tid], variance, sigma)
                        for name, (rows, variance, sigma) in self.variants.items()}
            values = score_variants(
                predictions[indices], np.sum(direction * east_axis, axis=-1),
                track.measured_hz, track.training_mask, short, variants)
            weight = len(np.unique(np.floor(track.times_s))); weight_sum += weight
            for name, result in values.items():
                for arm, value in result["scores"].items(): totals[name][arm] += weight * value
                maxima[name] = max(maxima[name], result["quadrature"][
                    "maximum_candidate_loglik_absolute_difference"])
        row = {"east_km": key[0], "north_km": key[1], "latitude_deg": lat,
               "longitude_deg": lon, "weight_seconds": weight_sum,
               "variant_scores": {name: {arm: total / weight_sum
                                  for arm, total in arms.items()}
                                  for name, arms in totals.items()},
               "quadrature_maximum_candidate_loglik_absolute_difference": maxima}
        self.cache[key] = row
        return row
