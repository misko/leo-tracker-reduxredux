"""Exclude time blocks before discovering tracks; score every excluded point."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import legval

from leo.analysis.polynomial_tracklets import TrackConfig, fit_lane


def wrapped_normal(residual, sigma, period):
    residual = (np.asarray(residual) + period / 2) % period - period / 2
    images = int(np.ceil(8 * sigma / period)) + 1
    density = np.zeros_like(residual)
    for shift in range(-images, images + 1):
        density += np.exp(-0.5 * ((residual + shift * period) / sigma) ** 2)
    return density / (sigma * np.sqrt(2 * np.pi))


def score_predictions(result, training_t, test_t, test_y, config):
    """Proper circular density with fixed 20% clutter and equal active-track weights.

    Tracks are active only inside their observed training support. No held-out
    point is used to extend a track, select a branch, or choose a noise scale.
    """
    predictions = []
    for track in result["tracks"]:
        prediction = np.full(len(test_t), np.nan)
        for piece in track["pieces"]:
            support = training_t[np.asarray(piece["indices"], int)]
            lower, upper = support.min(), support.max()
            if "join_time_s" in piece:
                knot = piece["join_time_s"]
                lower, upper = min(lower, knot), max(upper, knot)
            active = (test_t >= lower) & (test_t <= upper)
            x = (test_t[active] - piece["reference_time_s"]) / piece["time_scale_s"]
            prediction[active] = legval(x, piece["coefficients_hz"])
        predictions.append(prediction)
    if not predictions:
        return np.zeros(len(test_t)), np.full(len(test_t), np.inf), np.zeros(len(test_t), int)
    prediction = np.array(predictions)
    active = np.isfinite(prediction)
    residual = (
        test_y[None, :] - np.where(active, prediction, 0) + config.alias_spacing_hz / 2
    ) % config.alias_spacing_hz - config.alias_spacing_hz / 2
    signal = np.where(
        active, wrapped_normal(residual, config.noise_sigma_hz, config.alias_spacing_hz), 0
    ).sum(axis=0)
    count = active.sum(axis=0)
    uniform = 1 / config.alias_spacing_hz
    density = np.where(count > 0, 0.2 * uniform + 0.8 * signal / np.maximum(count, 1), uniform)
    nearest = np.min(np.where(active, np.abs(residual), np.inf), axis=0)
    return np.log(density / uniform), nearest, count


def cross_validate(rows, config, fitter=fit_lane, folds=4, block_s=5.0):
    """Run discovery independently for every fold and lane, with no membership reuse."""
    started = time.perf_counter()
    log_gain, nearest, active_counts, fold_rows = [], [], [], []
    for fold in range(folds):
        total_test, total_tracks = 0, 0
        for rx in (1, 2):
            for channel in range(1, 9):
                group = [r for r in rows if (r["receiver"], r["channel"]) == (rx, channel)]
                t = np.array([r["time_s"] for r in group])
                y = np.array([r["measured_cfo_hz"] for r in group])
                test = (np.floor(t / block_s).astype(int) % folds) == fold
                if not np.any(test):
                    continue
                fitted = fitter(t[~test], y[~test], config)
                gain, distance, count = score_predictions(
                    fitted, t[~test], t[test], y[test], config
                )
                log_gain.extend(gain.tolist())
                nearest.extend(distance.tolist())
                active_counts.extend(count.tolist())
                total_tracks += len(fitted["tracks"])
                total_test += int(test.sum())
        fold_rows.append(
            {
                "fold": fold,
                "excluded_points": total_test,
                "training_discovered_tracks_across_lanes": total_tracks,
            }
        )
        print(f"degree<={config.max_degree} fold {fold}: {total_test} excluded points", flush=True)
    assert len(log_gain) == len(rows), "Every original observation must be scored exactly once"
    distance = np.asarray(nearest)
    supported = distance < config.association_sigma * config.noise_sigma_hz
    return {
        "config": asdict(config),
        "observations": len(rows),
        "folds": fold_rows,
        "mean_log_density_gain_over_uniform_nats": float(np.mean(log_gain)),
        "total_log_density_gain_over_uniform_nats": float(np.sum(log_gain)),
        "points_with_active_prediction": int(np.count_nonzero(active_counts)),
        "points_within_3sigma_of_training_prediction": int(supported.sum()),
        "predictive_coverage_fraction": float(supported.mean()),
        "mean_active_tracks_per_excluded_point": float(np.mean(active_counts)),
        "nearest_residual_median_hz_when_prediction_exists": (
            float(np.median(distance[np.isfinite(distance)]))
            if np.isfinite(distance).any()
            else None
        ),
        "runtime_s": time.perf_counter() - started,
    }


def main():
    from evaluate_polynomial_tracklets import DEFAULT_INPUT, REPO, digest, load_observations

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core_path = REPO / "src/leo/analysis/polynomial_tracklets.py"
    core_hash = digest(core_path)
    rows, provenance = load_observations(DEFAULT_INPUT)
    config = TrackConfig()
    results = [cross_validate(rows, cfg) for cfg in (config, replace(config, max_degree=1))]
    if digest(core_path) != core_hash:
        raise RuntimeError("Fitter changed during cross-validation; rerun on frozen source")
    document = {
        "provenance": {
            **provenance,
            "fitter_sha256": core_hash,
            "validation_script_sha256": digest(Path(__file__)),
        },
        "protocol": (
            "Four folds of disjoint 5-second time blocks: floor(time_s/5)%4. "
            "Discover tracks from training observations only; score every excluded point once. "
            "Fixed 150Hz noise, fixed 20% circular-uniform clutter, equal active-track weights. "
            "No extrapolation outside training support. No labels or full-data memberships."
        ),
        "limits": (
            "Development evidence on an already inspected scan. Predictive coverage means "
            "proximity to at least one training curve, not verified identity. Predictive density "
            "penalizes multi-track alternatives. Noise and clutter mixture are assumptions."
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    for result in results:
        compact = {k: v for k, v in result.items() if k not in ("config", "folds")}
        print(json.dumps(compact), flush=True)


if __name__ == "__main__":
    main()
