#!/usr/bin/env python3
"""Timing-grid and robust-loss ablations for frozen sixteen-scan finalists.

The numerical helpers deliberately accept already-computed prediction tensors.  This
keeps catalogue propagation and location search in the shared harness while ensuring
that every ablation uses identical tracks, masks, identities and geographic points.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar


@dataclass(frozen=True)
class AblationConfig:
    timing_step_s: float
    objective: str
    identity_selection: str
    uncertainty_floor_hz: float = 250.0
    huber_delta: float = 1.5
    unmatched_penalty_hz: float = 800.0


def fractional_prediction(prediction_hz, source_taus_s, step_s):
    """Linearly interpolate a dense nuisance grid inside the sealed +/-5 s bank."""
    values = np.asarray(prediction_hz, dtype=float)
    source = np.asarray(source_taus_s, dtype=float)
    if values.ndim != 3 or values.shape[1] != len(source):
        raise ValueError("prediction must be candidate,tau,observation")
    source_step = np.diff(source)
    if (
        step_s not in (1.0, 0.5, 0.25)
        or not len(source_step)
        or not np.allclose(source_step, source_step[0])
        or source_step[0] > step_s + 1e-12
    ):
        raise ValueError("source timing grid must be uniform and at least as fine as target")
    target = np.arange(-5.0, 5.0 + step_s / 2, step_s)
    if source[0] != -5 or source[-1] != 5:
        raise ValueError("source timing bank must span exactly [-5,+5] seconds")
    out = np.empty((values.shape[0], len(target), values.shape[2]), dtype=float)
    for candidate in range(values.shape[0]):
        for observation in range(values.shape[2]):
            out[candidate, :, observation] = np.interp(
                target, source, values[candidate, :, observation]
            )
    return target, out


def pseudo_huber(value, delta=1.5):
    value = np.asarray(value, dtype=float)
    return delta**2 * (np.sqrt(1.0 + (value / delta) ** 2) - 1.0)


def robust_offset(residual_hz, sigma_hz, mask, delta=1.5):
    residual = np.asarray(residual_hz, dtype=float)[mask]
    sigma = np.asarray(sigma_hz, dtype=float)[mask]
    lower, upper = float(np.min(residual)), float(np.max(residual))
    if lower == upper:
        return lower
    fit = minimize_scalar(
        lambda offset: float(np.mean(pseudo_huber((residual - offset) / sigma, delta))),
        bounds=(lower, upper),
        method="bounded",
        options={"xatol": 1e-6, "maxiter": 80},
    )
    return float(fit.x)


def score_track(
    measured_hz,
    prediction_hz,
    training_mask,
    uncertainty_hz,
    candidate_ids,
    source_taus_s,
    config,
    *,
    visible=None,
):
    measured = np.asarray(measured_hz, dtype=float)
    training = np.asarray(training_mask, dtype=bool)
    uncertainty = np.asarray(uncertainty_hz, dtype=float)
    sigma = np.hypot(uncertainty, config.uncertainty_floor_hz)
    taus, prediction = fractional_prediction(prediction_hz, source_taus_s, config.timing_step_s)
    if measured.shape != training.shape or measured.shape != uncertainty.shape:
        raise ValueError("observation arrays differ")
    if not np.any(training) or not np.any(~training) or np.any(sigma <= 0):
        raise ValueError("positive uncertainty and nonempty randomized partitions required")
    allowed = np.ones(prediction.shape[:2], dtype=bool)
    if visible is not None:
        original = np.asarray(visible, dtype=bool)
        if original.ndim == 1:
            allowed = np.broadcast_to(original[:, None], allowed.shape).copy()
        elif original.shape == (prediction.shape[0], len(source_taus_s)):
            # Conservative: a fractional point is allowed only if both bracketing
            # integer states passed the common visibility gate.
            for j, tau in enumerate(taus):
                left = int(np.searchsorted(source_taus_s, np.floor(tau)))
                right = int(np.searchsorted(source_taus_s, np.ceil(tau)))
                allowed[:, j] = original[:, left] & original[:, right]
        else:
            raise ValueError("visibility shape differs")
    robust = config.objective == "uncertainty-floor-pseudo-huber"
    residual_bank = measured[None, None, :] - prediction
    if robust:
        offsets = np.mean(residual_bank[..., training], axis=-1)
        for _ in range(12):
            standardized = (residual_bank[..., training] - offsets[..., None]) / sigma[training]
            weights = 1.0 / (
                sigma[training] ** 2 * np.sqrt(1.0 + (standardized / config.huber_delta) ** 2)
            )
            offsets = np.sum(weights * residual_bank[..., training], axis=-1) / np.sum(
                weights, axis=-1
            )
    else:
        offsets = np.mean(residual_bank[..., training], axis=-1)
    centered = residual_bank - offsets[..., None]
    train_rms = np.sqrt(np.mean(centered[..., training] ** 2, axis=-1))
    eval_rms = np.sqrt(np.mean(centered[..., ~training] ** 2, axis=-1))
    train_robust = np.mean(
        pseudo_huber(centered[..., training] / sigma[training], config.huber_delta), axis=-1
    )
    eval_robust = np.mean(
        pseudo_huber(centered[..., ~training] / sigma[~training], config.huber_delta), axis=-1
    )
    training_metric = train_robust if robust else train_rms
    training_metric = np.where(allowed, training_metric, np.inf)
    usable = np.any(np.isfinite(training_metric), axis=1)
    if not np.any(usable):
        return None
    # Tau is always a training-profiled nuisance. The legacy parity variant may
    # select identity using evaluation RMS, but it must never select tau on it.
    tau_indices = np.argmin(training_metric, axis=1)
    profiled = []
    for candidate in np.flatnonzero(usable):
        tau_index = int(tau_indices[candidate])
        ordered = np.sort(training_metric[candidate])
        profiled.append(
            {
                "candidate_index": int(candidate),
                "candidate_id": str(candidate_ids[candidate]),
                "tau_s": float(taus[tau_index]),
                "offset_hz": float(offsets[candidate, tau_index]),
                "training_rms_hz": float(train_rms[candidate, tau_index]),
                "evaluation_rms_hz": float(eval_rms[candidate, tau_index]),
                "training_robust_loss": float(train_robust[candidate, tau_index]),
                "evaluation_robust_loss": float(eval_robust[candidate, tau_index]),
                "tau_training_margin": float(ordered[1] - ordered[0]),
            }
        )
    train_key = "training_robust_loss" if robust else "training_rms_hz"
    selection_key = (
        train_key
        if config.identity_selection == "training"
        else ("evaluation_robust_loss" if robust else "evaluation_rms_hz")
    )
    winner = min(
        profiled,
        key=lambda row: (row[selection_key], row[train_key], row["candidate_id"], row["tau_s"]),
    )
    winner["timing_at_bound"] = bool(np.isclose(abs(winner["tau_s"]), 5.0))
    winner["uncertainty_hz"] = float(np.median(uncertainty))
    winner["effective_sigma_hz"] = float(np.median(sigma))
    return winner


def summarize_tracks(track_rows, config):
    matched = [row for row in track_rows if row.get("winner") is not None]
    total_weight = float(sum(row["weight_s"] for row in track_rows))
    if config.objective == "duration-capped-rmse-800hz":
        loss = (
            sum(
                row["weight_s"]
                * min(
                    config.unmatched_penalty_hz
                    if row.get("winner") is None
                    else row["winner"]["evaluation_rms_hz"],
                    config.unmatched_penalty_hz,
                )
                ** 2
                for row in track_rows
            )
            / total_weight
        )
        value = float(np.sqrt(loss))
    else:
        unmatched = float(
            pseudo_huber(
                config.unmatched_penalty_hz / config.uncertainty_floor_hz, config.huber_delta
            )
        )
        value = float(
            sum(
                row["weight_s"]
                * (
                    unmatched
                    if row.get("winner") is None
                    else row["winner"]["evaluation_robust_loss"]
                )
                for row in track_rows
            )
            / total_weight
        )
    taus = np.asarray([row["winner"]["tau_s"] for row in matched], dtype=float)
    margins = np.asarray([row["winner"]["tau_training_margin"] for row in matched], dtype=float)
    offsets = np.asarray([row["winner"]["offset_hz"] for row in matched], dtype=float)
    sigmas = np.asarray([row["winner"]["effective_sigma_hz"] for row in matched], dtype=float)
    return {
        "objective_value": value,
        "matched_track_count": len(matched),
        "unmatched_track_count": len(track_rows) - len(matched),
        "tau_boundary_count": int(np.sum(np.isclose(np.abs(taus), 5.0))),
        "tau_abs_quantiles_s": (
            np.quantile(np.abs(taus), [0, 0.5, 0.9, 1]).tolist() if len(taus) else []
        ),
        "tau_training_margin_quantiles": (
            np.quantile(margins, [0, 0.5, 0.9, 1]).tolist() if len(margins) else []
        ),
        "frequency_offset_abs_quantiles_hz": (
            np.quantile(np.abs(offsets), [0, 0.5, 0.9, 1]).tolist() if len(offsets) else []
        ),
        "effective_sigma_quantiles_hz": (
            np.quantile(sigmas, [0, 0.5, 0.9, 1]).tolist() if len(sigmas) else []
        ),
    }


def training_roughness_uncertainty_hz(times_s, measured_hz, training_mask):
    """Training-only robust scatter about a linear frequency trajectory."""
    times = np.asarray(times_s, dtype=float)
    measured = np.asarray(measured_hz, dtype=float)
    training = np.asarray(training_mask, dtype=bool)
    design = np.column_stack(
        (np.ones(np.sum(training)), times[training] - np.mean(times[training]))
    )
    coefficient = np.linalg.lstsq(design, measured[training], rcond=None)[0]
    residual = measured[training] - design @ coefficient
    centre = np.median(residual)
    sigma = 1.4826 * np.median(np.abs(residual - centre))
    return float(max(sigma, 1.0))


def run_cache_ablation(cache, locations_path, output):
    """Evaluate every objective on identical cache tracks and supplied finalists."""
    module_path = Path(__file__).with_name("sixteen_joint_compare.py")
    spec = importlib.util.spec_from_file_location("sixteen_joint_compare", module_path)
    joint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(joint)
    manifest = json.loads((cache / "cache_manifest.json").read_text())
    locations = json.loads(locations_path.read_text())
    if isinstance(locations, dict):
        locations = locations["locations"]
    configs = [
        AblationConfig(step, "duration-capped-rmse-800hz", selection)
        for selection in ("evaluation", "training")
        for step in (1.0, 0.5, 0.25)
    ] + [
        AblationConfig(step, "uncertainty-floor-pseudo-huber", "training")
        for step in (1.0, 0.5, 0.25)
    ]
    started = time.monotonic()
    results, diagnostics = [], []
    for location in locations:
        cached_tracks = []
        for scan in manifest["scans"]:
            evidence, arrays = joint.load_scan_cache(cache, scan["session_id"])
            for track in evidence["tracks"]:
                prediction = joint.prediction_for_track(
                    evidence,
                    arrays,
                    track,
                    location["latitude_deg"],
                    location["longitude_deg"],
                    taus_s=np.arange(-5.0, 5.0001, 0.25),
                )
                uncertainty = training_roughness_uncertainty_hz(
                    prediction.times_s, prediction.measured_hz, prediction.training_mask
                )
                cached_tracks.append((scan["session_id"], prediction, uncertainty))
        for config in configs:
            method_started = time.monotonic()
            track_rows = []
            for session_id, prediction, uncertainty in cached_tracks:
                winner = score_track(
                    prediction.measured_hz,
                    prediction.predictions_hz,
                    prediction.training_mask,
                    np.full(len(prediction.measured_hz), uncertainty),
                    prediction.candidate_ids,
                    prediction.taus_s,
                    config,
                    visible=prediction.visible,
                )
                track_rows.append(
                    {
                        "session_id": session_id,
                        "track_id": prediction.track_id,
                        "observations": len(prediction.observation_ids),
                        "weight_s": int(len(np.unique(np.floor(prediction.times_s).astype(int)))),
                        "winner": winner,
                    }
                )
            summary = summarize_tracks(track_rows, config)
            method = (
                f"timing-{config.timing_step_s:g}s-{config.objective}-"
                f"identity-{config.identity_selection}"
            )
            results.append(
                {
                    "method": method,
                    "location_id": location.get("location_id", location.get("label")),
                    "prior": location.get("prior"),
                    "latitude_deg": location["latitude_deg"],
                    "longitude_deg": location["longitude_deg"],
                    "objective_name": config.objective,
                    "objective_value": summary["objective_value"],
                    "track_count": len(track_rows),
                    "observation_count": sum(row["observations"] for row in track_rows),
                    "scope": "conditional shared-finalist/per-scan prior-selected candidate union",
                    "runtime_s": time.monotonic() - method_started,
                    "timing_step_s": config.timing_step_s,
                    "error_km": location.get("error_km"),
                    "identity_selection": config.identity_selection,
                    **summary,
                }
            )
            diagnostics.append(
                {"method": method, "prior": location.get("prior"), "tracks": track_rows}
            )
    document = {
        "schema": "frozen16-timing-robust-ablation/v1",
        "complete": True,
        "position_truth_used_for_inference_or_tuning": False,
        "candidate_scope": manifest["candidate_scope"],
        "cache_manifest_sha256": "sha256:"
        + hashlib.sha256((cache / "cache_manifest.json").read_bytes()).hexdigest(),
        "location_scope": "fixed finalists supplied by shared-position comparison",
        "validation_scope": "conditional reused randomized evaluation; not untouched validation",
        "uncertainty_model": (
            "training-only per-track MAD scatter about linear CFO trend, combined in quadrature "
            "with predeclared 250 Hz floor; sensitivity model, not calibrated uncertainty"
        ),
        "fractional_timing": "exact 0.25 s propagated state grid with linear state interpolation",
        "results": results,
        "runtime_s": time.monotonic() - started,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.json").write_text(json.dumps(document, indent=2) + "\n")
    (output / "track_diagnostics.json.gz").write_bytes(
        gzip.compress((json.dumps(diagnostics, indent=2) + "\n").encode(), mtime=0)
    )
    from matplotlib.figure import Figure

    figure = Figure(figsize=(10, 4), layout="constrained")
    axes = figure.subplots(1, 2)
    for location in locations:
        location_id = location.get("location_id", location.get("label"))
        label = str(location_id or "finalist")
        rows = [row for row in results if row["location_id"] == location_id]
        for axis, objective in zip(
            axes,
            ("duration-capped-rmse-800hz", "uncertainty-floor-pseudo-huber"),
            strict=True,
        ):
            selected = [
                row
                for row in rows
                if row["objective_name"] == objective
                and (
                    row["identity_selection"] == "evaluation"
                    if objective.startswith("duration")
                    else True
                )
            ]
            selected.sort(key=lambda row: row["timing_step_s"])
            axis.plot(
                [row["timing_step_s"] for row in selected],
                [row["objective_value"] for row in selected],
                "o-",
                label=label,
            )
    axes[0].set(ylabel="Capped duration-weighted RMS (Hz)")
    axes[1].set(ylabel="Mean pseudo-Huber loss (dimensionless)")
    for axis in axes:
        axis.set(xlabel="Timing step (s)", xticks=[0.25, 0.5, 1.0])
        axis.grid(alpha=0.25)
        axis.legend()
    figure.savefig(output / "timing_robust.png", dpi=160)
    (output / "README.md").write_text(
        "# Frozen-16 timing and robust-loss ablation\n\n"
        "This is a fixed-finalist, candidate-pool-conditional comparison on the exact "
        "553 tracks and 14,043 observations. It is not a full-catalogue global search. "
        "The 1, 0.5 and 0.25 second timing grids all remain within ±5 seconds. Tau and "
        "frequency offset are fitted using the saved randomized training mask. The legacy "
        "rows retain evaluation-selected identity for production parity; separate train-only "
        "rows expose that selection dependence.\n\n"
        "The robust sensitivity uses training-only per-track frequency roughness plus a "
        "predeclared 250 Hz floor and pseudo-Huber loss (delta 1.5). It is not a calibrated "
        "measurement uncertainty model. Reused evaluation rows are conditional diagnostics, "
        "not untouched validation. See `results.json`, `track_diagnostics.json.gz`, and "
        "`timing_robust.png`.\n"
    )
    return document


def _self_test():
    measured = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])
    source = np.arange(-5.0, 5.01, 0.25)
    prediction = np.zeros((2, len(source), 6))
    prediction[0] = source[None, :, None] * 2 + np.arange(6)[None, None, :] * 2
    prediction[1] = 1000
    mask = np.array([1, 0, 1, 0, 1, 0], dtype=bool)
    config = AblationConfig(0.25, "duration-capped-rmse-800hz", "training")
    row = score_track(measured, prediction, mask, np.zeros(6), [1, 2], source, config)
    assert row["candidate_id"] == "1" and abs(row["training_rms_hz"]) < 1e-12
    assert row["tau_s"] == -5.0  # constant offset makes tau structurally unidentifiable here

    # Exact parity with the production scorer for the legacy identity-selection
    # behavior: tau/offset are training-profiled, identity uses evaluation RMS.
    from leo.analysis.adaptive_tle_position import (
        AdaptiveTrackPrediction,
        score_track_prediction,
    )

    rng = np.random.default_rng(727)
    source = np.arange(-5.0, 6.0)
    measured = rng.normal(size=12) * 200
    prediction = rng.normal(size=(4, 11, 12)) * 200
    mask = np.array(([True] * 7) + ([False] * 5))
    expected = score_track_prediction(
        AdaptiveTrackPrediction(
            "test",
            tuple(f"o{i}" for i in range(12)),
            np.arange(12, dtype=float),
            measured,
            mask,
            np.arange(4).astype(str),
            source,
            prediction,
            np.ones(4, dtype=bool),
        )
    )
    actual = score_track(
        measured,
        prediction,
        mask,
        np.zeros(12),
        np.arange(4),
        source,
        AblationConfig(1.0, "duration-capped-rmse-800hz", "evaluation"),
    )
    assert actual["candidate_id"] == expected.candidate_id
    assert actual["tau_s"] == expected.tau_s
    assert np.isclose(actual["evaluation_rms_hz"], expected.heldout_rms_hz)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--locations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        started = time.monotonic()
        _self_test()
        print(json.dumps({"ok": True, "elapsed_s": time.monotonic() - started}))
        return
    if args.cache and args.locations and args.output:
        result = run_cache_ablation(args.cache, args.locations, args.output)
        print(json.dumps({"results": len(result["results"]), "runtime_s": result["runtime_s"]}))
        return
    parser.error("provide --cache, --locations and --output (or --self-test)")


if __name__ == "__main__":
    main()
