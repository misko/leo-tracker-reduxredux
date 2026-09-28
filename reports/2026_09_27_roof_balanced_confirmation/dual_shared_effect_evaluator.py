"""Geographic scorer with shared detection and conditional-ratio effects."""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np

import shared_effect_evaluator as detection_core
from ratio_random_intercept import candidate_ratio_loglik
from robust_core import train_shortlist


runner = detection_core.runner


def _logsumexp(values):
    values = np.asarray(values, float); maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def dual_shared_joint_heldout_score(predicted_hz, candidate_east, measured_hz,
                                    train_mask, shortlist, reception_rows, *,
                                    ratio_variance, detection_sigma, ratio_tau,
                                    fit_order=64, verify_order=128,
                                    quadrature_tolerance=.001):
    """Replace conditional-ratio iid density with one shared ratio effect."""
    base = detection_core.shared_joint_heldout_score(
        predicted_hz, candidate_east, measured_hz, train_mask, shortlist,
        reception_rows, ratio_variance=ratio_variance,
        detection_sigma=detection_sigma, fit_order=fit_order,
        verify_order=verify_order, quadrature_tolerance=quadrature_tolerance)
    tau = float(ratio_tau)
    if not math.isfinite(tau) or tau < 0:
        raise ValueError("ratio_tau must be finite and nonnegative")
    if tau == 0.:
        result = dict(base); result["ratio_tau"] = 0.
        return result

    east = np.asarray(candidate_east, float)
    indices = np.asarray(shortlist["candidate_indices"], int)
    normal_residuals = []; reverse_residuals = []
    for row in reception_rows:
        if not row["matched"]: continue
        observation = int(row["observation_index"])
        x = east[indices, observation]
        observed = float(row["log_margin_ratio_rx1_rx0"])
        intercept = float(row["ratio_mean_east0"])
        slope = float(row["ratio_east_slope"])
        normal_residuals.append(observed - (intercept + slope * x))
        reverse_residuals.append(observed - (intercept - slope * x))
    candidates = len(indices)
    normal = np.asarray(normal_residuals, float).T if normal_residuals else np.empty((candidates, 0))
    reverse = np.asarray(reverse_residuals, float).T if reverse_residuals else np.empty((candidates, 0))
    ratio = candidate_ratio_loglik(normal, ratio_variance, tau)
    reverse_ratio = candidate_ratio_loglik(reverse, ratio_variance, tau)
    frequency = np.asarray(base["candidate_frequency_log_likelihood"], float)
    detection = np.asarray(base["candidate_detection_log_likelihood"], float)
    reverse_detection = np.asarray(
        base["candidate_reversed_detection_log_likelihood"], float)
    log_weights = np.asarray(shortlist["log_weights"], float)
    reserve = int(base["reserve_observations"])
    def score(extra):
        return float(-_logsumexp(log_weights + frequency + extra) / reserve)
    result = dict(base)
    result.update({
        "scores": {
            "D": base["scores"]["D"],
            "D_plus_detection": base["scores"]["D_plus_detection"],
            "D_plus_geometry": score(detection + ratio),
            "D_plus_reversed_geometry": score(reverse_detection + reverse_ratio),
        },
        "candidate_ratio_log_likelihood": ratio.tolist(),
        "candidate_reversed_ratio_log_likelihood": reverse_ratio.tolist(),
        "ratio_tau": tau,
    })
    return result


def score_variants(predictions, east, measured, training, shortlist, variants):
    values = {name: dual_shared_joint_heldout_score(
        predictions, east, measured, training, shortlist, rows,
        ratio_variance=variance, detection_sigma=sigma, ratio_tau=tau)
              for name, (rows, variance, sigma, tau) in variants.items()}
    d = [result["scores"]["D"] for result in values.values()]
    if not d or not np.allclose(d, d[0], rtol=0, atol=1e-12):
        raise ValueError("reception variants changed frequency score")
    return values


class DualSharedEffectEvaluator(detection_core.SharedEffectEvaluator):
    """Paired evaluator accepting variants (rows, variance, sigma, tau)."""

    def __init__(self, banks, origin, variants, parameters):
        compatibility = {name: (rows, variance, sigma)
                         for name, (rows, variance, sigma, _tau) in variants.items()}
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
            variants = {name: (rows[tid], variance, sigma, tau)
                        for name, (rows, variance, sigma, tau) in self.variants.items()}
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
