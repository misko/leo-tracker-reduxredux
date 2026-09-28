"""Per-track decomposition for fixed-point reception-geometry diagnostics."""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np

import paired_reception_evaluator as paired
from robust_core import train_shortlist, joint_heldout_score


runner = paired.runner


def posterior_summary(candidate_ids: object, log_evidence: object) -> dict[str, object]:
    ids = np.asarray(candidate_ids, dtype=int)
    values = np.asarray(log_evidence, dtype=float)
    if (ids.ndim != 1 or values.shape != ids.shape or not len(ids) or
            len(set(ids.tolist())) != len(ids) or not np.all(np.isfinite(values))):
        raise ValueError("posterior candidate IDs/evidence are invalid")
    maximum = float(np.max(values))
    log_normalizer = maximum + math.log(float(np.sum(np.exp(values - maximum))))
    normalized = values - log_normalizer
    probability = np.exp(normalized)
    order = np.argsort(-probability, kind="stable")
    first = int(order[0])
    second = int(order[1]) if len(order) > 1 else first
    positive = probability > 0
    entropy = -float(np.sum(probability[positive] * normalized[positive]))
    return {
        "candidate_ids": ids.tolist(),
        "normalized_log_weights": normalized.tolist(),
        "probabilities": probability.tolist(),
        "map_candidate_index": first,
        "map_candidate_id": int(ids[first]),
        "entropy_nats": entropy,
        "effective_candidates": float(math.exp(entropy)),
        "top_probability_margin": float(probability[first] - probability[second]),
        "top_log_weight_margin": (float(normalized[first] - normalized[second])
                                  if len(order) > 1 else None),
    }


class TrackDiagnosticEvaluator(paired.PairedEvaluator):
    """Paired evaluator retaining candidate-aligned per-track likelihoods."""

    def evaluate(self, east, north):
        key = (float(east), float(north))
        if key in self.cache:
            return self.cache[key]
        lat, lon = runner.base.coordinates(*self.origin, *key)
        receiver = runner.base.point(lat, lon).ecef_km
        east_axis = np.array([-np.sin(np.deg2rad(lon)),
                              np.cos(np.deg2rad(lon)), 0.])
        blocks = defaultdict(list)
        for block in self.predictions(*key):
            blocks[block.track_id].append(block)
        totals = {name: defaultdict(float) for name in self.variants}
        weight_sum = 0
        details = []
        for track_id, bank in self.banks.items():
            track = bank.source
            chunks = blocks[track_id]
            predictions = np.concatenate(
                [block.predictions_hz[:, 0, :] for block in chunks])
            ids = np.concatenate([block.candidate_ids for block in chunks])
            visible = np.concatenate([block.visible for block in chunks])
            shortlist = train_shortlist(
                predictions, track.measured_hz, track.training_mask, visible,
                scale_hz=self.parameters["scale_hz"],
                df=self.parameters["degrees_of_freedom"])
            indices = np.asarray(shortlist["candidate_indices"], dtype=int)
            chosen_ids = ids[indices].astype(int)
            short = dict(shortlist, candidate_indices=list(range(len(indices))))
            positions = bank.position_km[
                [self.index[track_id][int(candidate)] for candidate in chosen_ids],
                0, :, :]
            delta = positions - receiver
            direction = delta / np.linalg.norm(delta, axis=-1, keepdims=True)
            candidate_east = np.sum(direction * east_axis, axis=-1)
            weight = len(np.unique(np.floor(track.times_s)))
            reserve_count = int(np.count_nonzero(~np.asarray(track.training_mask, bool)))
            weight_sum += weight
            variant_details = {}
            frequency_summary = None
            for name, (rows, variance) in self.variants.items():
                result = joint_heldout_score(
                    predictions[indices], candidate_east, track.measured_hz,
                    track.training_mask, short, rows[track_id],
                    ratio_variance=variance)
                for arm, value in result["scores"].items():
                    totals[name][arm] += weight * value
                frequency = np.asarray(result["candidate_frequency_log_likelihood"], float)
                detection = np.asarray(result["candidate_detection_log_likelihood"], float)
                ratio = np.asarray(result["candidate_ratio_log_likelihood"], float)
                log_weights = np.asarray(short["log_weights"], float)
                current_frequency = posterior_summary(
                    chosen_ids, log_weights + frequency)
                if frequency_summary is None:
                    frequency_summary = current_frequency
                elif current_frequency != frequency_summary:
                    raise ValueError("reception variant changed frequency posterior")
                joint = posterior_summary(
                    chosen_ids, log_weights + frequency + detection + ratio)
                scores = dict(result["scores"])
                variant_details[name] = {
                    "scores": scores,
                    "candidate_frequency_log_likelihood": frequency.tolist(),
                    "candidate_detection_log_likelihood": detection.tolist(),
                    "candidate_ratio_log_likelihood": ratio.tolist(),
                    "frequency_posterior_log_weights": current_frequency[
                        "normalized_log_weights"],
                    "joint_posterior_log_weights": joint["normalized_log_weights"],
                    "frequency_map_candidate_id": current_frequency["map_candidate_id"],
                    "joint_map_candidate_id": joint["map_candidate_id"],
                    "frequency_posterior_entropy_nats": current_frequency["entropy_nats"],
                    "joint_posterior_entropy_nats": joint["entropy_nats"],
                    "frequency_top_probability_margin": current_frequency[
                        "top_probability_margin"],
                    "joint_top_probability_margin": joint["top_probability_margin"],
                    "detection_score_increment": (
                        scores["D_plus_detection"] - scores["D"]),
                    "conditional_ratio_score_increment": (
                        scores["D_plus_geometry"] - scores["D_plus_detection"]),
                    "matched_reception_observations": int(
                        result["matched_reception_observations"]),
                    "reception_observations": int(result["reception_observations"]),
                }
            details.append({
                "track_id": track_id,
                "weight_seconds": int(weight),
                "reserve_observations": reserve_count,
                "candidate_ids": chosen_ids.tolist(),
                "log_weights": list(short["log_weights"]),
                "training_weights": list(short["weights"]),
                "profiled_cfo_hz": list(short["profiled_cfo_hz"]),
                "training_rms_hz": list(short["training_rms_hz"]),
                "training_prior": posterior_summary(
                    chosen_ids, short["log_weights"]),
                "identity_interpretation": "model_association_not_decoded_truth",
                "variants": variant_details,
            })
        row = {
            "east_km": key[0], "north_km": key[1],
            "latitude_deg": lat, "longitude_deg": lon,
            "weight_seconds": weight_sum,
            "variant_scores": {
                name: {arm: total / weight_sum for arm, total in arms.items()}
                for name, arms in totals.items()},
            "tracks": details,
        }
        self.cache[key] = row
        return row
