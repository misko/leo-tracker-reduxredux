"""Training-map deletion diagnostics; no truth, orbit, or storage dependencies.

Input rows are externally defined evidence groups, such as complete scans.
Deletion stability is not calibrated confidence and cannot find unsampled modes.
"""

from __future__ import annotations

import numpy as np


def angular_distance_km(latitude_deg, longitude_deg, reference_index):
    latitude, longitude = np.deg2rad(latitude_deg), np.deg2rad(longitude_deg)
    delta = (
        np.sin((latitude - latitude[reference_index]) / 2) ** 2
        + np.cos(latitude)
        * np.cos(latitude[reference_index])
        * np.sin((longitude - longitude[reference_index]) / 2) ** 2
    )
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(delta, 0, 1)))


def regional_deletion_stability(
    training_log_evidence,
    latitude_deg,
    longitude_deg,
    group_ids,
    *,
    separated_mode_km=100.0,
):
    """Drop whole evidence groups and reselect on the *same* sampled map.

    Receiver copies of one pass must not be supplied as independent groups.
    This function does not estimate a variance or imply group independence.
    Ties use input grid order, with tie multiplicity explicitly reported.
    All scores must be finite (include a finite unassigned alternative upstream).
    """
    scores = np.asarray(training_log_evidence, dtype=float)
    latitude = np.asarray(latitude_deg, dtype=float)
    longitude = np.asarray(longitude_deg, dtype=float)
    groups = tuple(group_ids)
    if scores.ndim != 2 or min(scores.shape) < 1:
        raise ValueError("nonempty group by grid score matrix required")
    if latitude.shape != (scores.shape[1],) or longitude.shape != latitude.shape:
        raise ValueError("grid coordinate shapes do not match scores")
    if len(groups) != scores.shape[0] or len(set(groups)) != len(groups):
        raise ValueError("unique group identity required for each score row")
    if not all(np.all(np.isfinite(v)) for v in (scores, latitude, longitude)):
        raise ValueError("finite scores and coordinates required")
    if np.any(np.abs(latitude) > 90) or np.any(np.abs(longitude) > 180):
        raise ValueError("invalid geographic coordinates")
    if not np.isfinite(separated_mode_km) or separated_mode_km <= 0:
        raise ValueError("positive finite mode separation required")
    total = np.sum(scores, axis=0)
    best = int(np.argmax(total))
    distances = angular_distance_km(latitude, longitude, best)
    separated = distances >= separated_mode_km
    gap = float(total[best] - np.max(total[separated])) if np.any(separated) else None
    deleted = []
    if len(groups) > 1:
        for group, contribution in zip(groups, scores, strict=True):
            remaining = total - contribution
            index = int(np.argmax(remaining))
            deleted.append(
                {
                    "omitted_group": group,
                    "grid_index": index,
                    "latitude_deg": float(latitude[index]),
                    "longitude_deg": float(longitude[index]),
                    "distance_from_full_best_km": float(distances[index]),
                    "exact_tie_count": int(np.sum(remaining == remaining[index])),
                }
            )
    return {
        "state": "diagnostic" if deleted else "insufficient-groups",
        "group_count": len(groups),
        "grid_count": len(latitude),
        "best_grid_index": best,
        "best_latitude_deg": float(latitude[best]),
        "best_longitude_deg": float(longitude[best]),
        "exact_tie_count": int(np.sum(total == total[best])),
        "separated_mode_km": float(separated_mode_km),
        "separated_mode_score_gap": gap,
        "deletions": deleted,
        "maximum_deletion_displacement_km": max(
            (row["distance_from_full_best_km"] for row in deleted), default=None
        ),
        "calibrated_uncertainty": False,
        "scope": "fixed sampled training grid; unsampled modes are untested",
    }
