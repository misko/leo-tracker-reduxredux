"""Predeclared calibration-only advancement gate; no geographic outcomes."""
from __future__ import annotations

import math

MODELS = ("M0", "mean", "mixture")
TOLERANCE = 1e-8  # NLL per equally weighted track; avoid numerical-noise wins.


def evaluate_gate(folds: list[dict], expected_sessions: list[str]) -> dict:
    if len(expected_sessions) != 6 or len(set(expected_sessions)) != 6:
        raise ValueError("expected exactly six distinct calibration sessions")
    ids = [fold["session_id"] for fold in folds]
    if len(ids) != 6 or len(set(ids)) != 6 or set(ids) != set(expected_sessions):
        raise ValueError("missing, duplicate, or unexpected calibration fold")
    sums = {name: 0.0 for name in MODELS}
    total_tracks = 0
    gains = []
    converged = True
    for fold in sorted(folds, key=lambda item: item["session_id"]):
        count = fold["track_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("track count must be a positive integer")
        models = fold["models"]
        if set(models) != set(MODELS):
            raise ValueError("missing or unexpected model arm")
        for name in MODELS:
            loss = float(models[name]["joint_nll_sum"])
            status = models[name]["converged"]
            if not math.isfinite(loss) or not isinstance(status, bool):
                raise ValueError("invalid calibration loss or convergence flag")
            sums[name] += loss
            converged = converged and status
        gain = float(models["mean"]["joint_nll_sum"]) - float(
            models["mixture"]["joint_nll_sum"])
        gains.append({"session_id": fold["session_id"], "track_count": count,
                      "gain_nll_sum": gain, "gain_per_track": gain / count})
        total_tracks += count
    largest = max(gains, key=lambda item: (item["gain_nll_sum"], item["session_id"]))
    remaining_gain = (sums["mean"] - sums["mixture"] - largest["gain_nll_sum"]) / (
        total_tracks - largest["track_count"])
    improvements = sum(item["gain_per_track"] > TOLERANCE for item in gains)
    checks = {
        "all_folds_converged": converged,
        "pooled_better_than_M0": (sums["M0"] - sums["mixture"]) / total_tracks > TOLERANCE,
        "pooled_better_than_mean": (sums["mean"] - sums["mixture"]) / total_tracks > TOLERANCE,
        "at_least_four_scans_improve": improvements >= 4,
        "positive_after_removing_largest_gain": remaining_gain > TOLERANCE,
    }
    return {
        "advance": all(checks.values()), "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "track_count": total_tracks, "fold_count": len(folds),
        "pooled_nll_per_track": {name: loss / total_tracks for name, loss in sums.items()},
        "scan_gains": gains, "improving_scans": improvements,
        "removed_largest_gain_session": largest["session_id"],
        "remaining_gain_per_track": remaining_gain,
        "numerical_tolerance_per_track": TOLERANCE,
        "scope": "Conditional calibration LOSO only; not geographic validation or fully nested frequency validation.",
    }
