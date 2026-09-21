#!/usr/bin/env python3
"""Bounded circular-orbit sensitivity study for the LT3D-001A baseline."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

C_M_S = 299_792_458.0
EARTH_RADIUS_M = 6_378_137.0
EARTH_MU_M3_S2 = 3.986004418e14
EARTH_RATE_RAD_S = 7.2921150e-5
RF_HZ = 11_459_687_500.0
SOURCE_SEPARATION_HZ = 35_000.0
DT_S = (0.02, 0.12, 0.5, 9.0)
BASELINES_M = {
    "d0_mm": 0.080,
    "d50_mm": 0.080 + 2 * 0.050 * math.sin(math.radians(10)),
    "d100_mm": 0.080 + 2 * 0.100 * math.sin(math.radians(10)),
}
SCENARIOS = (
    ("LEO 350 km, eastward", 350_000.0, 90.0),
    ("LEO 550 km, 45-deg heading", 550_000.0, 45.0),
    ("LEO 1200 km, northward", 1_200_000.0, 0.0),
    ("MEO 20200 km, 45-deg heading", 20_200_000.0, 45.0),
)


def baseline_length_m(axial_offset_m: float) -> float:
    return 0.080 + 2 * axial_offset_m * math.sin(math.radians(10))


def phase_deg(frequency_hz: float, baseline_m: np.ndarray, los: np.ndarray) -> np.ndarray:
    return 360.0 * frequency_hz / C_M_S * np.sum(los * baseline_m, axis=-1)


def rotate_z(vectors: np.ndarray, angle: float | np.ndarray) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    x, y, z = np.moveaxis(vectors, -1, 0)
    return np.stack((c * x - s * y, s * x + c * y, z), axis=-1)


def observer_state(time_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Illustrative equatorial observer and its east/north/up basis in ECI."""
    angle = EARTH_RATE_RAD_S * time_s
    up = np.array([math.cos(angle), math.sin(angle), 0.0])
    east = np.array([-math.sin(angle), math.cos(angle), 0.0])
    north = np.array([0.0, 0.0, 1.0])
    return EARTH_RADIUS_M * up, east, north, up


def los_from_el_az(elevation_rad: np.ndarray, azimuth_rad: np.ndarray) -> np.ndarray:
    """ECI LOS at t=0; azimuth is east of north."""
    return np.stack(
        (
            np.sin(elevation_rad),
            np.cos(elevation_rad) * np.sin(azimuth_rad),
            np.cos(elevation_rad) * np.cos(azimuth_rad),
        ),
        axis=-1,
    )


def satellite_from_los(los: np.ndarray, altitude_m: float) -> np.ndarray:
    observer = np.array([EARTH_RADIUS_M, 0.0, 0.0])
    projection = los @ observer
    radius = EARTH_RADIUS_M + altitude_m
    distance = -projection + np.sqrt(projection**2 + radius**2 - EARTH_RADIUS_M**2)
    return observer + distance[:, None] * los


def orbit_velocity_direction(position: np.ndarray, heading_rad: np.ndarray) -> np.ndarray:
    desired = np.stack(
        (np.zeros_like(heading_rad), np.sin(heading_rad), np.cos(heading_rad)), axis=-1
    )
    radial = position / np.linalg.norm(position, axis=1)[:, None]
    tangent = desired - np.sum(desired * radial, axis=1)[:, None] * radial
    return tangent / np.linalg.norm(tangent, axis=1)[:, None]


def propagate_los(
    initial_los: np.ndarray, altitude_m: float, heading_rad: np.ndarray, time_s: float
) -> np.ndarray:
    position = satellite_from_los(initial_los, altitude_m)
    tangent = orbit_velocity_direction(position, heading_rad)
    radius = EARTH_RADIUS_M + altitude_m
    mean_motion = math.sqrt(EARTH_MU_M3_S2 / radius**3)
    propagated = position * math.cos(mean_motion * time_s) + radius * tangent * math.sin(
        mean_motion * time_s
    )
    observer, _, _, _ = observer_state(time_s)
    los = propagated - observer
    return los / np.linalg.norm(los, axis=1)[:, None]


def ideal_geo_los(initial_los: np.ndarray, time_s: float) -> np.ndarray:
    """An ideal geostationary control: a fixed direction in the local ECEF frame."""
    return rotate_z(initial_los, EARTH_RATE_RAD_S * time_s)


def offset_los(los: np.ndarray, separation_rad: float, bearing_rad: np.ndarray) -> np.ndarray:
    reference = np.broadcast_to(np.array([1.0, 0.0, 0.0]), los.shape)
    tangent_a = reference - np.sum(reference * los, axis=1)[:, None] * los
    weak = np.linalg.norm(tangent_a, axis=1) < 1e-8
    tangent_a[weak] = np.cross(np.array([0.0, 1.0, 0.0]), los[weak])
    tangent_a /= np.linalg.norm(tangent_a, axis=1)[:, None]
    tangent_b = np.cross(los, tangent_a)
    direction = np.cos(bearing_rad)[:, None] * tangent_a + np.sin(bearing_rad)[:, None] * tangent_b
    return math.cos(separation_rad) * los + math.sin(separation_rad) * direction


def summarize(values: np.ndarray, dt_s: float) -> dict[str, float]:
    q = np.quantile(values, (0.05, 0.25, 0.5, 0.75, 0.95))
    return {
        "q05_deg": float(q[0]),
        "q25_deg": float(q[1]),
        "median_deg": float(q[2]),
        "q75_deg": float(q[3]),
        "q95_deg": float(q[4]),
        "median_abs_deg": float(np.median(np.abs(values))),
        "q95_abs_deg": float(np.quantile(np.abs(values), 0.95)),
        "max_abs_deg": float(np.max(np.abs(values))),
        "median_abs_rate_deg_s": float(np.median(np.abs(values)) / dt_s),
        "q95_abs_rate_deg_s": float(np.quantile(np.abs(values), 0.95) / dt_s),
    }


def conservative_rate_bound_deg_s(altitude_m: float, baseline_m: float) -> float:
    """Orientation envelope from transverse satellite and observer speeds."""
    orbital_speed = math.sqrt(EARTH_MU_M3_S2 / (EARTH_RADIUS_M + altitude_m))
    angular_rate = (orbital_speed + EARTH_RATE_RAD_S * EARTH_RADIUS_M) / altitude_m
    angular_rate += EARTH_RATE_RAD_S  # baseline rotation in the inertial frame
    return 360.0 * RF_HZ / C_M_S * baseline_m * angular_rate


def beam_acceptance(los_a: np.ndarray, los_b: np.ndarray, half_angle_deg: float) -> np.ndarray:
    angle = math.radians(10)
    axes = np.array(
        [[math.cos(angle), -math.sin(angle), 0.0], [math.cos(angle), math.sin(angle), 0.0]]
    )
    threshold = math.cos(math.radians(half_angle_deg))
    return np.all(los_a @ axes.T >= threshold, axis=1) & np.all(los_b @ axes.T >= threshold, axis=1)


def simulate(sample_count: int = 30_000, seed: int = 20260921) -> dict:
    rng = np.random.default_rng(seed)
    # Uniform solid angle in the stated visible cap means sin(elevation) is uniform.
    elevation = np.arcsin(rng.uniform(math.sin(math.radians(20.0)), 1.0, sample_count))
    azimuth = rng.uniform(0.0, 2 * math.pi, sample_count)
    initial_los = los_from_el_az(elevation, azimuth)
    baseline = np.array([0.0, BASELINES_M["d50_mm"], 0.0])
    body: dict = {
        "schema": "lt3d_phase_geometry_scenarios_v1",
        "seed": seed,
        "sample_count": sample_count,
        "constants": {
            "rf_hz": RF_HZ,
            "source_frequency_separation_hz": SOURCE_SEPARATION_HZ,
            "earth_radius_m": EARTH_RADIUS_M,
            "earth_rotation_rad_s": EARTH_RATE_RAD_S,
            "baselines_m": BASELINES_M,
            "time_intervals_s": DT_S,
        },
        "conditional_prior": {
            "observer": "illustrative equator; holder midpoint axis local up; baseline local east",
            "elevation": "uniform solid angle over 20..90 deg (sin(elevation) uniform)",
            "azimuth_deg": "uniform 0..360",
            "heading_jitter_deg": "uniform +/-15 about named heading",
            "interpretation": "geometry sensitivity ensemble, not an actual-sky probability",
        },
        "single_source": {},
        "double_difference": {},
        "beam_overlap_sensitivity": {},
        "orientation_envelope_bounds": {},
    }
    for name, altitude, nominal_heading in SCENARIOS:
        headings = np.radians(nominal_heading + rng.uniform(-15.0, 15.0, sample_count))
        scenario = {}
        for dt in DT_S:
            final_los = propagate_los(initial_los, altitude, headings, dt)
            final_baseline = rotate_z(baseline, EARTH_RATE_RAD_S * dt)
            changes = phase_deg(RF_HZ, final_baseline, final_los) - phase_deg(
                RF_HZ, baseline, initial_los
            )
            scenario[str(dt)] = summarize(changes, dt)
        body["single_source"][name] = scenario
        body["orientation_envelope_bounds"][name] = {
            baseline_name: {
                "single_source_rate_deg_s": conservative_rate_bound_deg_s(altitude, baseline_m),
                "two_source_dd_rate_deg_s": 2 * conservative_rate_bound_deg_s(altitude, baseline_m),
            }
            for baseline_name, baseline_m in BASELINES_M.items()
        }

    geo = {}
    for dt in DT_S:
        final_los = ideal_geo_los(initial_los, dt)
        # Baseline rotates with the observer; express both endpoints consistently in ECI.
        final_baseline = rotate_z(baseline, EARTH_RATE_RAD_S * dt)
        changes = phase_deg(RF_HZ, final_baseline, final_los) - phase_deg(
            RF_HZ, baseline, initial_los
        )
        geo[str(dt)] = summarize(changes, dt)
    body["single_source"]["ideal GEO, fixed ECEF"] = geo

    altitude, nominal_heading = 550_000.0, 45.0
    heading_a = np.radians(nominal_heading + rng.uniform(-15.0, 15.0, sample_count))
    bearing = rng.uniform(0.0, 2 * math.pi, sample_count)
    for separation_deg in (0.0, 5.0, 10.0, 20.0):
        second_los = offset_los(initial_los, math.radians(separation_deg), bearing)
        both_visible = second_los[:, 0] >= math.sin(math.radians(20.0))
        overlap_masks = {
            half: beam_acceptance(initial_los, second_los, half) for half in (15.0, 30.0, 60.0)
        }
        row = {}
        conditional_rows: dict[str, dict] = {
            str(half): {
                "acceptance_fraction": float(np.mean(mask)),
                "conditional_double_difference": {},
            }
            for half, mask in overlap_masks.items()
        }
        relations = {
            "common_heading": heading_a,
            "independent_same_heading_band": np.radians(
                nominal_heading + rng.uniform(-15.0, 15.0, sample_count)
            ),
            "independent_unrestricted_heading": rng.uniform(0.0, 2 * math.pi, sample_count),
        }
        for relation, heading_b in relations.items():
            times = {}
            for dt in DT_S:
                final_a = propagate_los(initial_los, altitude, heading_a, dt)
                final_b = propagate_los(second_los, altitude, heading_b, dt)
                final_baseline = rotate_z(baseline, EARTH_RATE_RAD_S * dt)
                dd_initial = phase_deg(RF_HZ + SOURCE_SEPARATION_HZ, baseline, second_los)
                dd_initial -= phase_deg(RF_HZ, baseline, initial_los)
                dd_final = phase_deg(RF_HZ + SOURCE_SEPARATION_HZ, final_baseline, final_b)
                dd_final -= phase_deg(RF_HZ, final_baseline, final_a)
                dd_change = dd_final - dd_initial
                times[str(dt)] = summarize(dd_change[both_visible], dt)
                if dt in (0.12, 9.0):
                    for half, mask in overlap_masks.items():
                        selected = mask & both_visible
                        conditional_rows[str(half)]["conditional_double_difference"].setdefault(
                            relation, {}
                        )[str(dt)] = (
                            summarize(dd_change[selected], dt) if np.any(selected) else None
                        )
            row[relation] = times
        body["double_difference"][str(separation_deg)] = row
        body["beam_overlap_sensitivity"][str(separation_deg)] = conditional_rows

    same_final = propagate_los(initial_los, altitude, heading_a, 9.0)
    final_baseline = rotate_z(baseline, EARTH_RATE_RAD_S * 9.0)
    equal_frequency = phase_deg(RF_HZ, final_baseline, same_final) - phase_deg(
        RF_HZ, final_baseline, same_final
    )
    separated_frequency = (
        SOURCE_SEPARATION_HZ
        / RF_HZ
        * (phase_deg(RF_HZ, final_baseline, same_final) - phase_deg(RF_HZ, baseline, initial_los))
    )
    body["common_source_controls"] = {
        "equal_frequency_9s_max_abs_deg": float(np.max(np.abs(equal_frequency))),
        "35khz_separation_9s": summarize(separated_frequency, 9.0),
        "suppression_ratio_delta_f_over_f": SOURCE_SEPARATION_HZ / RF_HZ,
        "same_los_absolute_dd_envelope_deg": {
            name: 360.0 * SOURCE_SEPARATION_HZ / C_M_S * length
            for name, length in BASELINES_M.items()
        },
    }
    return body


def plot_report(body: dict, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.8), constrained_layout=True)
    colors = plt.cm.viridis(np.linspace(0.08, 0.92, len(body["single_source"])))
    times = np.array(DT_S)
    for color, (name, rows) in zip(colors, body["single_source"].items(), strict=True):
        med = [rows[str(t)]["median_abs_deg"] for t in times]
        hi = [rows[str(t)]["q95_abs_deg"] for t in times]
        label = f"{name} (zero; shown at plot floor)" if name.startswith("ideal GEO") else name
        axes[0].plot(times, np.maximum(med, 1e-5), marker="o", color=color, label=label)
        axes[0].plot(times, np.maximum(hi, 1e-5), linestyle="--", color=color, alpha=0.75)
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("interval (s)")
    axes[0].set_ylabel("|RX1−RX0 phase change| (deg)")
    axes[0].set_title("Single-source geometry\nsolid median; dashed 95th percentile")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=7)

    separations = [0.0, 5.0, 10.0, 20.0]
    for relation, marker in (
        ("common_heading", "o"),
        ("independent_same_heading_band", "s"),
        ("independent_unrestricted_heading", "^"),
    ):
        med = [
            body["double_difference"][str(s)][relation]["9.0"]["median_abs_deg"]
            for s in separations
        ]
        hi = [
            body["double_difference"][str(s)][relation]["9.0"]["q95_abs_deg"] for s in separations
        ]
        axes[1].plot(separations, med, marker=marker, label=f"{relation}: median")
        axes[1].plot(separations, hi, marker=marker, linestyle="--", label=f"{relation}: 95th")
    axes[1].axhspan(
        10.0,
        14.0,
        color="tab:red",
        alpha=0.12,
        label="observed visit change (~10–14°)",
    )
    axes[1].set_xlabel("initial angular separation (deg)")
    axes[1].set_ylabel("|double-difference change over 9 s| (deg)")
    axes[1].set_title("550 km conditional geometry\n35 kHz source-frequency separation")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=7)
    fig.suptitle(
        "LT3D-001A illustrative orbit-geometry phase distributions\n"
        "97.36 mm baseline; midpoint axis at zenith and baseline east",
        fontsize=13,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-png", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=30_000)
    args = parser.parse_args()
    body = simulate(args.samples)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    plot_report(body, args.output_png)


if __name__ == "__main__":
    main()
