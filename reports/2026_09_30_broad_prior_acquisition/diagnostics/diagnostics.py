#!/usr/bin/env python3
"""Likelihood-only diagnostics; reference coordinates never enter blind inference."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "reports/2026_09_30_gaussian_sum_64_scan"
sys.path.insert(0, str(SOURCE))
import physics  # noqa: E402
from leo.analysis.gaussian_sum_location import gaussian_logpdf  # noqa: E402


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_log_weights(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    maximum = np.max(values)
    weights = np.exp(values - maximum)
    return weights / weights.sum()


def en_from_geodetic(latitude: float, longitude: float, center_lat: float, center_lon: float):
    north = (latitude - center_lat) * 111.195
    east = (longitude - center_lon) * 111.195 * math.cos(math.radians(center_lat))
    return east, north


def load_unit(unit: str):
    evidence = json.loads((SOURCE / "evidence" / f"{unit}.json").read_text())
    metadata_path = SOURCE / "evidence" / f"{unit}-orbits.json"
    metadata = json.loads(metadata_path.read_text())
    state_path = SOURCE / "evidence" / f"{unit}-orbits.npz"
    if digest(state_path) != metadata["state_sha256"]:
        raise ValueError("orbit state digest mismatch")
    with np.load(state_path, allow_pickle=False) as data:
        bank = physics.OrbitBank(tuple(map(int, data["satellite_ids"])), data["knot_times_s"],
                                 data["positions_ecef_km"], data["velocities_ecef_km_s"])
    config = physics.PhysicsConfig(prior_center_lat_deg=38.5816, prior_center_lon_deg=-121.4944,
                                   support_radius_km=489.0)
    union = physics.geometric_candidate_union(bank, config)
    wanted = set(union.norad_ids)
    rows = np.array([i for i, value in enumerate(bank.norad_ids) if value in wanted])
    bank = physics.OrbitBank(tuple(bank.norad_ids[i] for i in rows), bank.times_s,
                             bank.positions_ecef_km[rows], bank.velocities_ecef_km_s[rows])
    return evidence, metadata, bank, config


def independent_tracks(evidence):
    spec = importlib.util.spec_from_file_location("frozen_runner", SOURCE / "run.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.independent_tracks(evidence)[0]


def diagnose_track(track, source_start_ns, bank, config, states):
    layout = physics.StateLayout(bank.norad_ids)
    times = (np.asarray(track["times_utc_ns"], dtype=np.int64) - source_start_ns) / 1e9
    observations = physics.TrackObservations(tuple(track["physical_observation_ids"]), times,
        np.asarray(track["measured_hz"]), np.full(len(times), track["receiver_id"], dtype=int), track["rf_hz"])
    built = physics.build_physics_factor(observations, bank, layout, config)
    factor = built.factor
    selected_times = times[np.asarray(built.selected_indices)]
    selected_receivers = observations.receiver_indices[np.asarray(built.selected_indices)]
    contrasts = physics.helmert_contrasts(selected_receivers)
    signal_covariance = contrasts @ physics._noise_covariance(selected_times, config) @ contrasts.T
    centered = selected_times - selected_times.mean()
    background_design = contrasts @ np.column_stack((centered, 0.5 * centered**2))
    background_covariance = signal_covariance + background_design @ np.diag(
        [config.background_slope_hz_s**2, config.background_curvature_hz_s2**2]
    ) @ background_design.T
    output = {"track_id": track["track_id"], "samples_used": len(factor.observation_ids),
              "observation_dimension": len(factor.observation),
              "observation_span_s": float(times.max() - times.min()),
              "background_log_likelihood": float(factor.background_log_likelihood),
              "background_log_likelihood_per_dimension":
                  float(factor.background_log_likelihood / len(factor.observation)),
              "signal_covariance_eigenvalue_hz2_range":
                  [float(np.linalg.eigvalsh(signal_covariance)[0]),
                   float(np.linalg.eigvalsh(signal_covariance)[-1])],
              "background_covariance_eigenvalue_hz2_range":
                  [float(np.linalg.eigvalsh(background_covariance)[0]),
                   float(np.linalg.eigvalsh(background_covariance)[-1])],
              "background_to_signal_logdet_ratio":
                  float(np.linalg.slogdet(background_covariance)[1] -
                        np.linalg.slogdet(signal_covariance)[1]),
              "states": {}}
    for label, state in states.items():
        priors = np.asarray([candidate.prior(state) if callable(candidate.prior) else candidate.prior
                            for candidate in factor.candidates])
        background_prior = (factor.background_prior(state) if callable(factor.background_prior)
                            else factor.background_prior)
        active = np.flatnonzero(priors > 0)
        logs, identifiers, predictions = [], [], []
        for index in active:
            candidate = factor.candidates[index]
            prediction = candidate.predict(state)
            logs.append(math.log(priors[index]) + gaussian_logpdf(factor.observation - prediction.mean,
                                                                  prediction.covariance))
            identifiers.append(candidate.label)
            predictions.append(prediction)
        background_log = math.log(background_prior) + factor.background_log_likelihood
        all_logs = np.asarray(logs + [background_log])
        probabilities = normalized_log_weights(all_logs)
        signal_probabilities = probabilities[:-1]
        signal_mass = float(signal_probabilities.sum())
        conditional_signal = (signal_probabilities / signal_mass if signal_mass > 0
                              else np.zeros_like(signal_probabilities))
        entropy = float(-np.sum(conditional_signal[conditional_signal > 0] *
                                np.log(conditional_signal[conditional_signal > 0])))
        best = int(np.argmax(logs)) if logs else -1
        # This is deliberately a callback self-consistency check, not independent validation.
        synthetic = None
        if predictions:
            true_index = 0
            synthetic_logs = np.asarray([
                math.log(priors[index]) + gaussian_logpdf(predictions[true_index].mean - pred.mean,
                                                          pred.covariance)
                for index, pred in zip(active, predictions, strict=True)
            ])
            rank = int(np.sum(synthetic_logs > synthetic_logs[true_index]) + 1)
            synthetic = {"kind": "same_callback_wiring_check", "independent_forward_model": False,
                         "true_norad": identifiers[true_index], "rank": rank,
                         "posterior_probability_signal_only": float(normalized_log_weights(synthetic_logs)[true_index])}
        output["states"][label] = {
            "signal_prior_sum": float(priors.sum()), "background_prior": float(background_prior),
            "total_prior": float(priors.sum() + background_prior), "visible_candidates": len(active),
            "background_probability": float(probabilities[-1]),
            "conditional_signal_entropy_nats": entropy,
            "conditional_signal_effective_candidates": float(math.exp(entropy)),
            "best_signal_norad": None if best < 0 else identifiers[best],
            "best_signal_log_joint": None if best < 0 else float(logs[best]),
            "background_log_joint": float(background_log), "synthetic_known_identity": synthetic,
        }
    output["time_support_margin_s"] = float(min(times.min() - bank.times_s[1], bank.times_s[-2] - times.max()))
    return output


def run(units: list[str], max_tracks: int) -> dict:
    selection = json.loads((SOURCE / "selection.json").read_text())
    by_unit = {row["unit_id"]: row for rows in selection["selected"].values() for row in rows}
    results = []
    started = time.monotonic()
    for unit in units:
        evidence, metadata, bank, config = load_unit(unit)
        source = json.loads(Path(evidence["source"]["path"]).read_text())
        pose = json.loads((ROOT / "reports/2026_09_28_ds9_post_ds8/pose" /
                           f"{evidence['session_id']}.json").read_text())["pose_authority"]
        roof_e, roof_n = en_from_geodetic(pose["latitude_deg"], pose["longitude_deg"],
                                           config.prior_center_lat_deg, config.prior_center_lon_deg)
        layout = physics.StateLayout(bank.norad_ids)
        sacramento = np.zeros(layout.dimension)
        roof = sacramento.copy(); roof[:2] = roof_e, roof_n
        roof_high = roof.copy(); roof_high[2] = 1.0
        tracks = independent_tracks(evidence)[:max_tracks]
        rows = [diagnose_track(track, source["start_utc_ns"], bank, config,
                               {"sacramento_center_blind": sacramento,
                                "roof_reference_diagnostic": roof,
                                "roof_plus_1km_support_check": roof_high}) for track in tracks]
        results.append({"unit_id": unit, "session_id": evidence["session_id"],
                        "selection_binding": by_unit[unit]["manifest_sha256"],
                        "orbit_metadata_sha256": digest(SOURCE / "evidence" / f"{unit}-orbits.json"),
                        "candidate_count": len(bank.norad_ids), "roof_offset_en_km": [roof_e, roof_n],
                        "reference_use": "diagnostic_only_not_blind_inference", "tracks": rows})
    return {"schema": "broad-prior-likelihood-diagnostics/v1", "units": results,
            "max_tracks_per_unit": max_tracks, "wall_seconds": time.monotonic() - started,
            "likelihood_configuration": {
                "reference_frequency_hz": config.reference_frequency_hz,
                "white_noise_hz": config.white_noise_hz,
                "correlated_noise_hz": config.correlated_noise_hz,
                "correlation_time_s": config.correlation_time_s,
                "background_slope_hz_s": config.background_slope_hz_s,
                "background_curvature_hz_s2": config.background_curvature_hz_s2,
                "height_support_km": config.height_support_km,
                "time_padding_s": config.time_padding_s,
            },
            "source_code": {str(SOURCE / "physics.py"): digest(SOURCE / "physics.py"),
                            str(ROOT / "src/leo/analysis/gaussian_sum_location.py"):
                                digest(ROOT / "src/leo/analysis/gaussian_sum_location.py")}}


def plot(document, output: Path):
    import matplotlib.pyplot as plt
    rows = [(unit["unit_id"], track) for unit in document["units"] for track in unit["tracks"]]
    x = np.arange(len(rows)); width = .36
    sac = [track["states"]["sacramento_center_blind"]["background_probability"] for _, track in rows]
    roof = [track["states"]["roof_reference_diagnostic"]["background_probability"] for _, track in rows]
    fig, ax = plt.subplots(figsize=(11, 4.5)); ax.bar(x-width/2, sac, width, label="Sacramento blind center")
    ax.bar(x+width/2, roof, width, label="Roof reference diagnostic"); ax.set_ylabel("Background posterior probability")
    ax.set_xlabel("Chronological retained track"); ax.set_ylim(0, 1); ax.legend(); fig.tight_layout(); fig.savefig(output, dpi=160); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--units", nargs="+", required=True)
    parser.add_argument("--max-tracks", type=int, default=8); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = run(args.units, args.max_tracks); args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n"); plot(result, args.output.with_suffix(".png"))
    print(json.dumps({"output":str(args.output),"seconds":result["wall_seconds"]}))


if __name__ == "__main__": main()
