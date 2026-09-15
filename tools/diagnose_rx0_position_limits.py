#!/usr/bin/env python3
"""Work backward from a blind Doppler position fit to its limiting evidence."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
from pathlib import Path

import matplotlib
import numpy as np
from polish_regional_doppler import digest, load_observations, state_arrays

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets


def fitted_centre(values: np.ndarray, training: np.ndarray) -> np.ndarray:
    return values - np.mean(values[training])


def doppler(position: np.ndarray, velocity: np.ndarray, receiver: np.ndarray) -> np.ndarray:
    delta = position - receiver
    return (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * velocity, axis=-1)
        / np.linalg.norm(delta, axis=-1)
    )


def local_basis(latitude_deg: float, longitude_deg: float) -> tuple[np.ndarray, ...]:
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    east = np.array([-np.sin(longitude), np.cos(longitude), 0.0])
    north = np.array(
        [
            -np.sin(latitude) * np.cos(longitude),
            -np.sin(latitude) * np.sin(longitude),
            np.cos(latitude),
        ]
    )
    up = np.array(
        [
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        ]
    )
    return east, north, up


def sky_angle(
    position: np.ndarray, receiver: np.ndarray, basis: tuple[np.ndarray, ...]
) -> tuple[float, float]:
    unit = (position - receiver) / np.linalg.norm(position - receiver)
    east, north, up = basis
    azimuth = math.degrees(math.atan2(unit @ east, unit @ north)) % 360
    elevation = math.degrees(math.asin(np.clip(unit @ up, -1, 1)))
    return azimuth, elevation


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def quantiles(values: list[float]) -> dict[str, float]:
    q = np.quantile(values, [0.1, 0.25, 0.5, 0.75, 0.9])
    return {
        key: float(value) for key, value in zip(("p10", "p25", "p50", "p75", "p90"), q, strict=True)
    }


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Tie-free rank correlation for continuous diagnostics."""
    ranks_a = np.argsort(np.argsort(a, kind="stable"), kind="stable")
    ranks_b = np.argsort(np.argsort(b, kind="stable"), kind="stable")
    return float(np.corrcoef(ranks_a, ranks_b)[0, 1])


def track_sampling_summary(recording_review: Path) -> dict:
    intervals, spans, points = [], [], []
    file_count = 0
    for path in recording_review.glob("scan-hop-*.json.gz"):
        file_count += 1
        document = json.loads(gzip.decompress(path.read_bytes()))
        for track in document["screen"]["tracks"]:
            times = np.sort(np.asarray(track["time_s"], dtype=float))
            intervals.extend(np.diff(times).tolist())
            spans.append(float(track["span_s"]))
            points.append(int(track["observations"]))
    return {
        "recording_count": file_count,
        "track_count": len(points),
        "median_observations": float(np.median(points)),
        "median_span_s": float(np.median(spans)),
        "median_observation_interval_s": float(np.median(intervals)),
    }


def analyze(
    experiment: Path,
    output: Path,
    truth: tuple[float, float],
    recording_review: Path,
) -> dict:
    if output.exists():
        raise ValueError("output must be fresh")
    output.mkdir(parents=True)
    run = experiment / "8h-refine5"
    evidence = experiment / "evidence-v3"
    parent = json.loads((run / "result.json").read_text())
    history = json.loads((run / "history.json").read_text())
    polish_path = experiment / "8h-polish.json"
    polish = json.loads(polish_path.read_text())
    model = next(row for row in polish["models"] if not row["fit_orbit_time"])
    estimate = (model["latitude_deg"], model["longitude_deg"])
    estimate_receiver = geodetic_to_ecef_km(*estimate, 0.0)
    truth_receiver = geodetic_to_ecef_km(*truth, -29.0)
    basis = local_basis(*estimate)
    delta_km = 0.01
    assignment = {(row["session_id"], row["episode_id"]): row for row in polish["assignments"]}
    catalogues: dict[str, tuple[object, dict[int, int]]] = {}
    rows = []
    normal = np.zeros((2, 2))
    displacement_mse = []
    for scan in history:
        session_id = scan["session_id"]
        source_path = evidence / "evidence" / f"{session_id}.json"
        document = json.loads(source_path.read_text())
        metadata = document["inventory"]
        tle_path = source_path.parent / metadata["tle_file"]
        key = metadata["tle_digest"]
        if key not in catalogues:
            catalogue = parse_element_sets(tle_path.read_text())
            catalogues[key] = (
                catalogue,
                {number: i for i, number in enumerate(catalogue.satellite_numbers)},
            )
        catalogue, number_index = catalogues[key]
        for episode_id, arc in load_observations(document, 0, parent["individual_sources"]):
            chosen = assignment.get((session_id, episode_id))
            if chosen is None:
                continue
            norad = chosen["norad"]
            positions, velocities, valid = state_arrays(
                catalogue,
                [number_index[norad]],
                metadata["reference_utc_ns"],
                arc.time_s,
            )
            if len(valid) != 1:
                raise ValueError("frozen assignment no longer propagates")
            position, velocity = positions[0], velocities[0]
            predicted = doppler(position, velocity, estimate_receiver)
            residual = fitted_centre(arc.frequency_hz - predicted, arc.training)
            truth_prediction = doppler(position, velocity, truth_receiver)
            displacement = fitted_centre(truth_prediction - predicted, arc.training)
            derivatives = []
            for direction in basis[:2]:
                plus = doppler(position, velocity, estimate_receiver + delta_km * direction)
                minus = doppler(position, velocity, estimate_receiver - delta_km * direction)
                derivatives.append(fitted_centre((plus - minus) / (2 * delta_km), arc.training))
            jacobian = np.column_stack(derivatives)
            train_jacobian = jacobian[arc.training]
            train_residual = residual[arc.training]
            weight = 1 / len(train_residual) / 250.0**2
            robust = 1 / np.sqrt(1 + (train_residual / 250.0) ** 2)
            normal += train_jacobian.T @ ((weight * robust)[:, None] * train_jacobian)
            displacement_mse.append(float(np.mean(displacement**2)))
            middle = len(position) // 2
            azimuth, elevation = sky_angle(position[middle], estimate_receiver, basis)
            rows.append(
                {
                    "session_id": session_id,
                    "episode_id": episode_id,
                    "norad": norad,
                    "channel": document["series"][
                        next(
                            i
                            for i, item in enumerate(document["series"])
                            if item["tracklet_id"] == episode_id
                        )
                    ]["channel"],
                    "edge": document["series"][
                        next(
                            i
                            for i, item in enumerate(document["series"])
                            if item["tracklet_id"] == episode_id
                        )
                    ]["edge"],
                    "points": len(arc.time_s),
                    "span_s": float(np.ptp(arc.time_s)),
                    "azimuth_deg": azimuth,
                    "elevation_deg": elevation,
                    "training_rms_hz": rms(residual[arc.training]),
                    "heldout_rms_hz": rms(residual[~arc.training]),
                    "position_sensitivity_hz_per_km": rms(np.linalg.norm(jacobian, axis=1)),
                    "truth_displacement_signature_rms_hz": rms(displacement),
                }
            )
    covariance = np.linalg.inv(normal)
    eigenvalues = np.linalg.eigvalsh(covariance)
    azimuth_rad = np.deg2rad([row["azimuth_deg"] for row in rows])
    vector = np.mean(np.exp(1j * azimuth_rad))
    heldout = np.array([row["heldout_rms_hz"] for row in rows])
    elevation = np.array([row["elevation_deg"] for row in rows])
    sensitivity = np.array([row["position_sensitivity_hz_per_km"] for row in rows])
    span = np.array([row["span_s"] for row in rows])
    gate_sensitivity = load_gate_sensitivity(experiment, truth)
    summary = {
        "scientific_status": "retrospective diagnostic with blind-fit identities frozen",
        "position_fit_digest": digest(polish_path),
        "episode_count": len(rows),
        "estimate": {"latitude_deg": estimate[0], "longitude_deg": estimate[1]},
        "truth": {"latitude_deg": truth[0], "longitude_deg": truth[1]},
        "heldout_rms_hz": model["heldout_rms_hz"],
        "per_episode_heldout_rms_hz": quantiles(heldout.tolist()),
        "position_sensitivity_hz_per_km": quantiles(sensitivity.tolist()),
        "truth_displacement_signature_rms_hz": float(np.sqrt(np.mean(displacement_mse))),
        "model_internal_formal_axes_km": np.sqrt(eigenvalues).tolist(),
        "formal_covariance_warning": (
            "conditional linearized scale; excludes association, TLE, UTC, "
            "oscillator and correlation systematics"
        ),
        "sky": {
            "elevation_deg": quantiles(elevation.tolist()),
            "azimuth_resultant_length": float(abs(vector)),
            "azimuth_preferred_deg": float(
                math.degrees(math.atan2(vector.imag, vector.real)) % 360
            ),
            "quadrant_counts": quadrant_counts(np.rad2deg(azimuth_rad) % 360),
        },
        "spearman": {
            "heldout_rms_vs_elevation": spearman(heldout, elevation),
            "heldout_rms_vs_span": spearman(heldout, span),
            "heldout_rms_vs_sensitivity": spearman(heldout, sensitivity),
        },
        "association_stability_near_truth": association_stability(run, history, truth),
        "training_gate_sensitivity": gate_sensitivity,
        "published_track_sampling": track_sampling_summary(recording_review),
    }
    with (output / "episode-diagnostics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    render(rows, summary, output)
    return summary


def quadrant_counts(azimuth_deg: np.ndarray) -> dict[str, int]:
    return {
        "N": int(np.sum((azimuth_deg >= 315) | (azimuth_deg < 45))),
        "E": int(np.sum((azimuth_deg >= 45) & (azimuth_deg < 135))),
        "S": int(np.sum((azimuth_deg >= 135) & (azimuth_deg < 225))),
        "W": int(np.sum((azimuth_deg >= 225) & (azimuth_deg < 315))),
    }


def load_gate_sensitivity(experiment: Path, truth: tuple[float, float]) -> dict:
    def row(path: Path, kind: str, value: float) -> dict:
        document = json.loads(path.read_text())
        model = next(item for item in document["models"] if not item["fit_orbit_time"])
        return {
            "gate": kind,
            "value": value,
            "episode_count": document["episode_count"],
            "orbit_group_count": document["orbit_group_count"],
            "horizontal_error_km": haversine_km(
                (model["latitude_deg"], model["longitude_deg"]), truth
            ),
            "training_rms_hz": model["training_rms_hz"],
            "heldout_rms_hz": model["heldout_rms_hz"],
            "converged": model["converged"],
            "source_digest": digest(path),
        }

    rms_rows = []
    for path in experiment.glob("8h-polish-rms*.json"):
        match = re.fullmatch(r"8h-polish-rms([0-9.]+)\.json", path.name)
        if match:
            rms_rows.append(row(path, "maximum_training_rms_hz", float(match.group(1))))
    rms_rows.append(row(experiment / "8h-polish.json", "maximum_training_rms_hz", 500.0))
    elevation_rows = []
    for path in experiment.glob("8h-polish-elevation*-v2.json"):
        match = re.fullmatch(r"8h-polish-elevation([0-9.]+)-v2\.json", path.name)
        if match:
            elevation_rows.append(
                row(path, "minimum_training_elevation_deg", float(match.group(1)))
            )
    elevation_rows.append(
        row(experiment / "8h-polish.json", "minimum_training_elevation_deg", -90.0)
    )
    return {
        "rms": sorted(rms_rows, key=lambda item: item["value"]),
        "elevation": sorted(elevation_rows, key=lambda item: item["value"]),
        "selection_uses_heldout_or_truth": False,
    }


def association_stability(run: Path, history: list[dict], truth: tuple[float, float]) -> dict:
    grid = np.load(run / "grid.npz")
    best = json.loads((run / "result.json").read_text())["best_index"]
    distance = np.array(
        [
            haversine_km((lat, lon), truth)
            for lat, lon in zip(grid["latitude_deg"], grid["longitude_deg"], strict=True)
        ]
    )
    truth_cell = int(np.argmin(distance))
    compared = same = 0
    for scan in history:
        arrays = np.load(run / f"{scan['session_id']}.npz")
        eligible = (arrays["signal_weight"][:, best] >= 0.95) & (
            arrays["best_train_rms_hz"][:, best] <= 500
        )
        compared += int(np.sum(eligible))
        same += int(
            np.sum(
                eligible & (arrays["best_norad"][:, best] == arrays["best_norad"][:, truth_cell])
            )
        )
    return {
        "compared_episodes": compared,
        "same_norad_count": same,
        "same_norad_fraction": same / compared,
        "nearest_truth_cell_error_km": float(distance[truth_cell]),
    }


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lat2 = np.deg2rad([a[0], b[0]])
    dlat, dlon = lat2 - lat1, np.deg2rad(b[1] - a[1])
    value = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return float(6371.0088 * 2 * np.arcsin(np.sqrt(value)))


def render(rows: list[dict], summary: dict, output: Path) -> None:
    elevation = np.array([row["elevation_deg"] for row in rows])
    azimuth = np.deg2rad([row["azimuth_deg"] for row in rows])
    heldout = np.array([row["heldout_rms_hz"] for row in rows])
    sensitivity = np.array([row["position_sensitivity_hz_per_km"] for row in rows])
    displacement = np.array([row["truth_displacement_signature_rms_hz"] for row in rows])
    fig = plt.figure(figsize=(15, 5.3), constrained_layout=True)
    polar = fig.add_subplot(131, projection="polar")
    scatter = polar.scatter(azimuth, 90 - elevation, c=np.log10(heldout), s=18, cmap="viridis")
    polar.set_theta_zero_location("N")
    polar.set_theta_direction(-1)
    polar.set_rlim(0, 90)
    polar.set_yticks([0, 15, 30, 45, 60, 75, 90])
    polar.set_yticklabels(["90°", "75°", "60°", "45°", "30°", "15°", "0°"])
    polar.set_title("Frozen candidate sky directions")
    fig.colorbar(scatter, ax=polar, label="log10 held-out RMS (Hz)", shrink=0.7)
    ax = fig.add_subplot(132)
    ax.scatter(elevation, heldout, s=18, alpha=0.65)
    ax.set(
        yscale="log",
        xlabel="Candidate midpoint elevation (deg)",
        ylabel="Held-out RMS (Hz)",
        title="Residual versus inferred elevation",
    )
    ax.grid(alpha=0.25)
    ax = fig.add_subplot(133)
    ax.scatter(sensitivity, displacement, c=elevation, s=18, alpha=0.7, cmap="plasma")
    ax.set(
        xscale="log",
        yscale="log",
        xlabel="Position sensitivity (Hz/km)",
        ylabel="6.79 km displacement signature (Hz)",
        title="Geographic signal in each trajectory",
    )
    ax.grid(alpha=0.25)
    fig.suptitle("RX0 10 MS/s positioning-limit diagnostics")
    fig.savefig(output / "01-residual-geometry.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), constrained_layout=True)
    axes[0].hist(heldout, bins=np.logspace(1, 4, 30), color="#3182bd")
    axes[0].set(
        xscale="log",
        xlabel="Per-episode held-out RMS (Hz)",
        ylabel="Episodes",
        title="Prediction error",
    )
    axes[1].hist(sensitivity, bins=25, color="#31a354")
    axes[1].set(
        xlabel="Position sensitivity (Hz/km)", ylabel="Episodes", title="Available local geometry"
    )
    axes[2].hist(displacement, bins=25, color="#e6550d")
    axes[2].axvline(
        summary["heldout_rms_hz"], color="black", linestyle="--", label="pooled held-out RMS"
    )
    axes[2].set(
        xlabel="Shape change at truth (Hz RMS)",
        ylabel="Episodes",
        title="Signal from correcting location",
    )
    axes[2].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.25)
    fig.savefig(output / "02-limit-budget.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), constrained_layout=True)
    for ax, key, label in (
        (axes[0], "rms", "Maximum training RMS (Hz)"),
        (axes[1], "elevation", "Minimum inferred elevation (deg)"),
    ):
        gate = summary["training_gate_sensitivity"][key]
        x = [item["value"] for item in gate]
        ax.plot(x, [item["horizontal_error_km"] for item in gate], "o-", label="position error")
        twin = ax.twinx()
        twin.plot(
            x,
            [item["heldout_rms_hz"] for item in gate],
            "s--",
            color="#e6550d",
            label="held-out RMS",
        )
        ax.set(xlabel=label, ylabel="Horizontal error (km)")
        twin.set_ylabel("Held-out RMS (Hz)", color="#e6550d")
        ax.grid(alpha=0.25)
    axes[0].set_title("Training-quality gate")
    axes[1].set_title("Zenith-field sensitivity")
    fig.suptitle("Lower residuals do not remove the location bias")
    fig.savefig(output / "03-training-gate-sensitivity.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--truth-lat", type=float, required=True)
    parser.add_argument("--truth-lon", type=float, required=True)
    parser.add_argument("--recording-review", type=Path, required=True)
    args = parser.parse_args()
    summary = analyze(
        args.experiment,
        args.output,
        (args.truth_lat, args.truth_lon),
        args.recording_review,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
