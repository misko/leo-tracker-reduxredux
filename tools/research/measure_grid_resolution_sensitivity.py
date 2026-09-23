#!/usr/bin/env python3
# ruff: noqa: E501, I001
"""Measure fixed-candidate Doppler sensitivity to grid-cell quantization.

This is a conditional geometry experiment. Candidate identities come from a
declared finalized Sacramento point and are never reselected while positions
move. It reports model-only and real-measurement residuals separately.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

import fast_coverage_inputs
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.contracts.sky import ObserverSiteV1
from search_multiresolution_tle_coverage import (
    build_prediction_banks,
    partition_mask,
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def offset_samples(count: int, seed: int) -> tuple[np.ndarray, list[str]]:
    """Return shared uniform cell phases and named center/edge/corner phases."""
    if count < 1:
        raise ValueError("positive uniform sample count required")
    uniform = np.random.default_rng(seed).uniform(-0.5, 0.5, size=(count, 2))
    special = np.asarray(
        [
            [0.0, 0.0],
            [-0.5, 0.0],
            [0.5, 0.0],
            [0.0, -0.5],
            [0.0, 0.5],
            [-0.5, -0.5],
            [-0.5, 0.5],
            [0.5, -0.5],
            [0.5, 0.5],
        ]
    )
    labels = [
        "center",
        "west_edge",
        "east_edge",
        "south_edge",
        "north_edge",
        "southwest_corner",
        "northwest_corner",
        "southeast_corner",
        "northeast_corner",
    ]
    return np.concatenate((uniform, special)), ["uniform"] * count + labels


def _doppler(position: np.ndarray, velocity: np.ndarray, sites) -> tuple[np.ndarray, np.ndarray]:
    """Return trial-by-tau-by-observation Doppler and exact visibility."""
    delta = position[None] - sites.ecef_km[:, None, None]
    distance = np.linalg.norm(delta, axis=-1)
    prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity[None], axis=-1) / distance
    sine = np.sum(delta * sites.up[:, None, None], axis=-1) / distance
    return prediction, np.max(sine, axis=(1, 2)) >= 0.0


def score_trials(
    measured_hz: np.ndarray,
    predictions_hz: np.ndarray,
    training: np.ndarray,
    visible: np.ndarray,
    fixed_tau_index: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fit the training-only offset and optionally refit tau for each trial."""
    measured = np.asarray(measured_hz, dtype=float)
    prediction = np.asarray(predictions_hz, dtype=float)
    mask = np.asarray(training, dtype=bool)
    if prediction.ndim != 3 or prediction.shape[2] != len(measured) or mask.shape != measured.shape:
        raise ValueError("trial prediction or training shape mismatch")
    if not 1 <= mask.sum() < len(mask):
        raise ValueError("both training and held-out rows required")
    residual = measured[None, None] - prediction
    offset = np.mean(residual[:, :, mask], axis=2)
    centered = residual - offset[:, :, None]
    train = np.sqrt(np.mean(centered[:, :, mask] ** 2, axis=2))
    if fixed_tau_index is None:
        tau = np.argmin(train, axis=1)
    else:
        if not 0 <= fixed_tau_index < prediction.shape[1]:
            raise ValueError("fixed tau index is outside prediction bank")
        tau = np.full(len(prediction), fixed_tau_index, dtype=int)
    rows = np.arange(len(prediction))
    held = np.sqrt(np.mean(centered[rows, tau][:, ~mask] ** 2, axis=1))
    held = np.where(visible, held, np.inf)
    return held, train[rows, tau], tau


def finite_summary(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if not len(finite):
        return {
            "median_hz": None,
            "p90_hz": None,
            "max_hz": None,
            "nonfinite_count": int(values.size),
        }
    return {
        "median_hz": float(np.median(finite)),
        "p90_hz": float(np.quantile(finite, 0.9)),
        "max_hz": float(np.max(finite)),
        "nonfinite_count": int(values.size - len(finite)),
    }


def coverage_summary(rms: np.ndarray, observation_counts: np.ndarray, threshold_hz: float) -> dict:
    qualified = rms < threshold_hz
    covered = np.sum(qualified * observation_counts[:, None], axis=0)
    return {
        "all_tracks_survive_fraction": float(np.mean(np.all(qualified, axis=0))),
        "pooled_track_survival_fraction": float(np.mean(qualified)),
        "unique_observation_coverage_median": float(np.median(covered)),
        "unique_observation_coverage_p10": float(np.quantile(covered, 0.1)),
        "unique_observation_coverage_min": int(np.min(covered)),
    }


def analytic_rms_coefficient(
    position: np.ndarray,
    velocity: np.ndarray,
    region: Region,
    east_km: float,
    north_km: float,
    tau_index: int,
    training: np.ndarray,
    step_km: float = 0.25,
) -> float:
    """Return tr(G)/12 for uniform-square quantization RMS²≈s² tr(G)/12."""
    coordinates = np.asarray(
        [
            [east_km - step_km, north_km],
            [east_km + step_km, north_km],
            [east_km, north_km - step_km],
            [east_km, north_km + step_km],
        ]
    )
    sites = region.points(coordinates[:, 0], coordinates[:, 1])
    prediction, _ = _doppler(position, velocity, sites)
    curve = prediction[:, tau_index]
    derivative = np.column_stack(
        ((curve[1] - curve[0]) / (2 * step_km), (curve[3] - curve[2]) / (2 * step_km))
    )
    held = ~training
    adjusted = derivative[held] - np.mean(derivative[training], axis=0)
    return float(np.trace(adjusted.T @ adjusted / np.sum(held)) / 12.0)


def load_anchor(path: Path) -> tuple[dict, list[dict]]:
    with gzip.open(path, "rt") as stream:
        rows = json.load(stream)
    if not rows or not rows[0].get("tracks"):
        raise ValueError("anchor finalists are empty")
    anchor = rows[0]
    tracks = []
    for row in anchor["tracks"]:
        candidate = row.get("best_candidate")
        if candidate is None:
            raise ValueError("anchor lacks a best candidate for one track")
        tracks.append(
            {
                "tracklet_id": row["tracklet_id"],
                "norad": int(candidate["norad"]),
                "tau_s": float(candidate["tau_s"]),
                "partition_seed": row["partition_seed"],
            }
        )
    return anchor, tracks


def run(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError(args.output)
    if tuple(args.spacings_km) != tuple(sorted(set(args.spacings_km))):
        raise ValueError("spacings must be increasing and unique")
    anchor, selected = load_anchor(args.anchor_finalists)
    import map_randomized_tle_coverage as frozen_kernel

    source_paths = {
        "sensitivity_tool": Path(__file__),
        "fast_search_engine": Path(build_prediction_banks.__code__.co_filename),
        "input_loader": Path(fast_coverage_inputs.__file__),
        "frozen_kernel": Path(frozen_kernel.__file__),
        "anchor_finalists": args.anchor_finalists,
    }
    source_digests = {name: digest(path) for name, path in source_paths.items()}
    region = Region(args.center_lat, args.center_lon, 5000.0, 5000.0)
    if not np.allclose([anchor["east_km"], anchor["north_km"]], args.anchor_offset_km, atol=1e-8):
        raise ValueError("anchor finalists do not match declared anchor offset")
    inputs = fast_coverage_inputs.load(args.session, args.evidence, args.bulk_root, args.tle_root)
    banks, bank_metadata = build_prediction_banks(inputs)
    by_track = {bank.tracklet_id: bank for bank in banks}
    taus = np.arange(-5.0, 6.0)
    anchor_site = region.points([args.anchor_offset_km[0]], [args.anchor_offset_km[1]])
    fixed_site = ObserverSiteV1(
        latitude_deg=float(anchor_site.latitude_deg[0]),
        longitude_deg=float(anchor_site.longitude_deg[0]),
        altitude_m=0.0,
        label="fast-coverage-cell",
    )
    phases, labels = offset_samples(args.uniform_samples, args.seed)
    frozen = []
    for choice in selected:
        bank = by_track.get(choice["tracklet_id"])
        if bank is None:
            raise ValueError("anchor track is absent from loaded banks")
        candidate = np.flatnonzero(bank.norads == choice["norad"])
        tau = np.flatnonzero(taus == choice["tau_s"])
        if len(candidate) != 1 or len(tau) != 1:
            raise ValueError("anchor candidate or tau is absent from frozen bank")
        mask, seed = partition_mask(
            bank.observation_ids,
            bank.support_digest,
            inputs["trajectory_digest"],
            fixed_site,
            mode="fixed",
        )
        if seed != choice["partition_seed"]:
            raise ValueError("anchor partition seed differs from fixed sensitivity protocol")
        position = bank.position_km[int(candidate[0])]
        velocity = bank.velocity_km_s[int(candidate[0])]
        anchor_prediction, _ = _doppler(position, velocity, anchor_site)
        synthetic = anchor_prediction[0, int(tau[0])]
        coefficient = analytic_rms_coefficient(
            position,
            velocity,
            region,
            args.anchor_offset_km[0],
            args.anchor_offset_km[1],
            int(tau[0]),
            mask,
        )
        frozen.append((bank, position, velocity, mask, synthetic, coefficient, choice))
    results = []
    observation_counts = np.asarray([len(item[0].observation_ids) for item in frozen])
    for spacing in args.spacings_km:
        points = np.asarray(args.anchor_offset_km)[None] + phases * spacing
        sites = region.points(points[:, 0], points[:, 1])
        real, model_refit, model_fixed = [], [], []
        chosen_tau_real, chosen_tau_model = [], []
        visibility = []
        for bank, position, velocity, mask, synthetic, _coefficient, choice in frozen:
            prediction, visible = _doppler(position, velocity, sites)
            held_real, _, tau_real = score_trials(bank.measured_hz, prediction, mask, visible)
            held_model, _, tau_model = score_trials(synthetic, prediction, mask, visible)
            fixed_index = int(np.flatnonzero(taus == choice["tau_s"])[0])
            held_fixed, _, _ = score_trials(
                synthetic,
                prediction,
                mask,
                visible,
                fixed_tau_index=fixed_index,
            )
            real.append(held_real)
            model_refit.append(held_model)
            model_fixed.append(held_fixed)
            chosen_tau_real.append(tau_real)
            chosen_tau_model.append(tau_model)
            visibility.append(visible)
        real = np.asarray(real)
        model_refit = np.asarray(model_refit)
        model_fixed = np.asarray(model_fixed)
        uniform = np.asarray(labels) == "uniform"
        special_rows = []
        for index in np.flatnonzero(~uniform):
            special_rows.append(
                {
                    "label": labels[index],
                    "east_offset_km": float(phases[index, 0] * spacing),
                    "north_offset_km": float(phases[index, 1] * spacing),
                    "model_tau_refit_heldout_rms_hz": [
                        float(value) if np.isfinite(value) else None
                        for value in model_refit[:, index]
                    ],
                    "model_fixed_anchor_tau_heldout_rms_hz": [
                        float(value) if np.isfinite(value) else None
                        for value in model_fixed[:, index]
                    ],
                    "measured_heldout_rms_hz": [
                        float(value) if np.isfinite(value) else None for value in real[:, index]
                    ],
                }
            )
        track_rows = []
        for index, (_, _, _, _, _, coefficient, choice) in enumerate(frozen):
            track_rows.append(
                {
                    **choice,
                    "model_tau_refit_uniform": finite_summary(model_refit[index, uniform]),
                    "model_fixed_anchor_tau_uniform": finite_summary(model_fixed[index, uniform]),
                    "measured_uniform": finite_summary(real[index, uniform]),
                    "model_tau_refit_200hz_survival_fraction": float(
                        np.mean(model_refit[index, uniform] < 200.0)
                    ),
                    "model_fixed_anchor_tau_200hz_survival_fraction": float(
                        np.mean(model_fixed[index, uniform] < 200.0)
                    ),
                    "measured_200hz_survival_fraction": float(
                        np.mean(real[index, uniform] < 200.0)
                    ),
                    "analytic_expected_model_rms_hz": float(spacing * np.sqrt(coefficient)),
                }
            )
        results.append(
            {
                "spacing_km": float(spacing),
                "uniform_sample_count": int(uniform.sum()),
                "uniform_model_tau_refit": {
                    "pooled_rms": finite_summary(model_refit[:, uniform]),
                    "coverage": coverage_summary(
                        model_refit[:, uniform], observation_counts, 200.0
                    ),
                },
                "uniform_model_fixed_anchor_tau": {
                    "pooled_rms": finite_summary(model_fixed[:, uniform]),
                    "coverage": coverage_summary(
                        model_fixed[:, uniform], observation_counts, 200.0
                    ),
                },
                "uniform_measured": {
                    "pooled_rms": finite_summary(real[:, uniform]),
                    "coverage": coverage_summary(real[:, uniform], observation_counts, 200.0),
                },
                "raw_uniform_by_track": [
                    {
                        "tracklet_id": choice["tracklet_id"],
                        "model_tau_refit_heldout_rms_hz": model_refit[index, uniform].tolist(),
                        "model_fixed_anchor_tau_heldout_rms_hz": model_fixed[
                            index, uniform
                        ].tolist(),
                        "measured_heldout_rms_hz": real[index, uniform].tolist(),
                        "real_selected_tau_index": chosen_tau_real[index][uniform].tolist(),
                        "model_selected_tau_index": chosen_tau_model[index][uniform].tolist(),
                        "exact_any_tau_visibility": visibility[index][uniform].tolist(),
                    }
                    for index, (*_, choice) in enumerate(frozen)
                ],
                "per_track": track_rows,
                "edges_and_corners": special_rows,
            }
        )
    result = {
        "schema": "grid-resolution-fixed-candidate-sensitivity/v1",
        "complete": True,
        "truth_accessed": False,
        "identity_selection": "fixed anchor finalists; no displaced-position reselection",
        "scientific_status": "conditional grid-quantization sensitivity, not identity proof or location confidence",
        "session_id": args.session,
        "anchor_offset_km": list(args.anchor_offset_km),
        "anchor_finalists": str(args.anchor_finalists),
        "anchor_finalists_digest": digest(args.anchor_finalists),
        "fixed_partition": "spatially independent fixed randomized 60/40; constant offset is refit on training rows only",
        "synthetic_tau_protocol": "reported both pipeline tau-refit over [-5,+5] s and fixed recorded anchor tau; synthetic baseline is the fixed anchor candidate/tau prediction",
        "uniform_phase_distribution": "shared deterministic U[-0.5,0.5]^2 phases, scaled by spacing",
        "special_phase_note": "edges/corners are explicitly reported; sampled maximum is not a certified global maximum",
        "visibility_note": "RMS is set nonfinite when exact sampled geometry has no above-horizon tau/observation; this is a conditional diagnostic, not a claim of full coarse-gate pipeline eligibility parity",
        "source_digests_before_compute": source_digests,
        "spacings_km": list(args.spacings_km),
        "uniform_samples": args.uniform_samples,
        "seed": args.seed,
        "input_provenance": inputs["provenance"],
        "prediction_bank": bank_metadata,
        "tool_digest": digest(Path(__file__)),
        "results": results,
    }
    source_digests_after = {name: digest(path) for name, path in source_paths.items()}
    if source_digests_after != source_digests:
        raise RuntimeError("source changed during sensitivity computation; refusing mixed receipt")
    result["source_digests_after_compute"] = source_digests_after
    args.output.mkdir(parents=True)
    shutil.copyfile(args.anchor_finalists, args.output / "anchor-finalists.json.gz")
    (args.output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="scan-fw-cf510316ae7f05d5")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--anchor-finalists", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--center-lat", type=float, default=38.5816)
    parser.add_argument("--center-lon", type=float, default=-121.4944)
    parser.add_argument("--anchor-offset-km", type=float, nargs=2, default=(-81.25, -81.25))
    parser.add_argument(
        "--spacings-km", type=float, nargs="+", default=(12.5, 25.0, 50.0, 100.0, 200.0, 400.0)
    )
    parser.add_argument("--uniform-samples", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20260923)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
