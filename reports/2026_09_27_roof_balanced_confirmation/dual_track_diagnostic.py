"""Per-track decomposition of fixed-position dual shared-effect scores."""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np

import dual_shared_effect_evaluator as dual
from mixture_track_diagnostic import posterior_summary
from robust_core import train_shortlist


runner = dual.runner


class DualTrackDiagnosticEvaluator(dual.DualSharedEffectEvaluator):
    """Dual evaluator retaining candidate-aligned evidence and associations."""

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
        tracks = []
        for track_id, bank in self.banks.items():
            track = bank.source; chunks = blocks[track_id]
            predictions = np.concatenate([b.predictions_hz[:, 0, :] for b in chunks])
            ids = np.concatenate([b.candidate_ids for b in chunks])
            visible = np.concatenate([b.visible for b in chunks])
            shortlist = train_shortlist(
                predictions, track.measured_hz, track.training_mask, visible,
                scale_hz=self.parameters["scale_hz"],
                df=self.parameters["degrees_of_freedom"])
            indices = np.asarray(shortlist["candidate_indices"], int)
            chosen_ids = ids[indices].astype(int)
            short = dict(shortlist, candidate_indices=list(range(len(indices))))
            positions = bank.position_km[
                [self.index[track_id][int(candidate)] for candidate in chosen_ids], 0, :, :]
            direction = ((positions - receiver) /
                         np.linalg.norm(positions - receiver, axis=-1, keepdims=True))
            candidate_east = np.sum(direction * east_axis, axis=-1)
            variants = {name: (rows[track_id], variance, sigma, tau)
                        for name, (rows, variance, sigma, tau) in self.variants.items()}
            values = dual.score_variants(
                predictions[indices], candidate_east, track.measured_hz,
                track.training_mask, short, variants)
            weight = len(np.unique(np.floor(track.times_s))); weight_sum += weight
            reserve_count = int(np.count_nonzero(~np.asarray(track.training_mask, bool)))
            variant_details = {}
            for name, result in values.items():
                if result["reserve_observations"] != reserve_count:
                    raise ValueError("core reserve count changed")
                receipt = result["quadrature"]
                maximum = float(receipt["maximum_candidate_loglik_absolute_difference"])
                tolerance = float(receipt["tolerance"])
                if (not receipt.get("passed") or
                        not math.isfinite(maximum) or not math.isfinite(tolerance) or
                        not 0 <= maximum <= tolerance <= .001):
                    raise ValueError("core quadrature receipt is not accepted")
                scores = dict(result["scores"])
                for arm, value in scores.items(): totals[name][arm] += weight * value
                maxima[name] = max(maxima[name], maximum)
                frequency = np.asarray(result["candidate_frequency_log_likelihood"], float)
                detection = np.asarray(result["candidate_detection_log_likelihood"], float)
                ratio = np.asarray(result["candidate_ratio_log_likelihood"], float)
                reverse_detection = np.asarray(
                    result["candidate_reversed_detection_log_likelihood"], float)
                reverse_ratio = np.asarray(
                    result["candidate_reversed_ratio_log_likelihood"], float)
                log_weights = np.asarray(short["log_weights"], float)
                frequency_posterior = posterior_summary(
                    chosen_ids, log_weights + frequency)
                joint = posterior_summary(
                    chosen_ids, log_weights + frequency + detection + ratio)
                reverse_joint = posterior_summary(
                    chosen_ids, log_weights + frequency + reverse_detection + reverse_ratio)
                variant_details[name] = {
                    "scores": scores,
                    "candidate_frequency_log_likelihood": frequency.tolist(),
                    "candidate_detection_log_likelihood": detection.tolist(),
                    "candidate_ratio_log_likelihood": ratio.tolist(),
                    "candidate_reversed_detection_log_likelihood": reverse_detection.tolist(),
                    "candidate_reversed_ratio_log_likelihood": reverse_ratio.tolist(),
                    "frequency_posterior_log_weights": frequency_posterior["normalized_log_weights"],
                    "frequency_posterior_probabilities": frequency_posterior["probabilities"],
                    "frequency_map_candidate_id": frequency_posterior["map_candidate_id"],
                    "joint_posterior_log_weights": joint["normalized_log_weights"],
                    "joint_posterior_probabilities": joint["probabilities"],
                    "joint_map_candidate_id": joint["map_candidate_id"],
                    "reversed_joint_posterior_log_weights": reverse_joint["normalized_log_weights"],
                    "reversed_joint_posterior_probabilities": reverse_joint["probabilities"],
                    "reversed_joint_map_candidate_id": reverse_joint["map_candidate_id"],
                    "frequency_posterior_entropy_nats": frequency_posterior["entropy_nats"],
                    "joint_posterior_entropy_nats": joint["entropy_nats"],
                    "quadrature": dict(result["quadrature"]),
                    "detection_sigma": float(result["detection_sigma"]),
                    "ratio_tau": float(result["ratio_tau"]),
                    "reception_observations": int(result["reception_observations"]),
                    "matched_reception_observations": int(
                        result["matched_reception_observations"]),
                }
            tracks.append({
                "track_id": track_id, "weight_seconds": int(weight),
                "reserve_observations": reserve_count,
                "candidate_ids": chosen_ids.tolist(),
                "log_weights": list(short["log_weights"]),
                "profiled_cfo_hz": list(short["profiled_cfo_hz"]),
                "training_rms_hz": list(short["training_rms_hz"]),
                "training_prior": posterior_summary(
                    chosen_ids, short["log_weights"]),
                "frequency_prior_map_candidate_id": int(chosen_ids[
                    int(np.argmax(short["log_weights"]))]),
                "identity_interpretation": "model_association_not_decoded_truth",
                "variants": variant_details,
            })
        row = {"east_km": key[0], "north_km": key[1], "latitude_deg": lat,
               "longitude_deg": lon, "weight_seconds": weight_sum,
               "variant_scores": {name: {arm: total / weight_sum
                                  for arm, total in arms.items()}
                                  for name, arms in totals.items()},
               "quadrature_maximum_candidate_loglik_absolute_difference": maxima,
               "tracks": tracks}
        self.cache[key] = row
        return row
