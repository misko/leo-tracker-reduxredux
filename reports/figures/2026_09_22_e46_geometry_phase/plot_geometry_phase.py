#!/usr/bin/env python3
"""Reproduce the conditional LT3D-001A geometric phase simulation for e46.

This is a report-only calculation.  It uses the frozen, causal element sets and
the published 12-visit timing.  It does not read or modify RF recordings.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from sgp4.api import Satrec

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    look_angles,
    teme_to_ecef,
)

C_M_S = 299_792_458.0
SITE = (37.858988, -122.478103, -29.0)
RF_HZ = 11_190_312_500.0
TRACK_START_UTC_NS = 1_789_994_224_176_276_795
VISITS = np.array([376, 453, 486, 513, 537, 564, 588, 614, 638, 668, 697, 724])
TIMES_S = np.array(
    [0.0, 9.7968004, 13.998552, 17.450626, 20.495472, 23.9285964,
     26.9698864, 30.2807628, 33.3435156, 37.170744, 40.8743328, 44.3066512]
)
BASELINES_M = {
    "mount centers, d=0 mm": 0.080,
    "illustrative d=50 mm": 0.080 + 2 * 0.050 * math.sin(math.radians(10.0)),
    "illustrative d=100 mm": 0.080 + 2 * 0.100 * math.sin(math.radians(10.0)),
}
CANDIDATES = {
    59925: {
        "label": "leading Doppler candidate 59925 (STARLINK-31959)",
        "tau_s": 1.0,
        "line1": "1 59925U 24106D   26263.85093421  .00001298  00000-0  56685-4 0  9998",
        "line2": "2 59925  43.0048 306.5158 0001592 267.6922  92.3748 15.27576664130411",
    },
    60188: {
        "label": "runner-up Doppler candidate 60188",
        "tau_s": -5.0,
        "line1": "1 60188U 24124F   26263.35622009  .00001523  00000-0  17426-4 0  9997",
        "line2": "2 60188  53.1585 281.9890 0001190  84.5596 275.5558 15.69713691127103",
    },
}


def states(number: int, elapsed_s: np.ndarray) -> dict[str, np.ndarray]:
    spec = CANDIDATES[number]
    satellite = Satrec.twoline2rv(spec["line1"], spec["line2"])
    receive_ns = TRACK_START_UTC_NS + np.rint(elapsed_s * 1e9).astype(np.int64)
    orbit_ns = receive_ns + round(spec["tau_s"] * 1e9)
    orbit_jd, orbit_fraction = julian_day_from_utc_ns(orbit_ns)
    error, position_teme, velocity_teme = satellite.sgp4_array(orbit_jd, orbit_fraction)
    if np.any(error != 0):
        raise RuntimeError(f"SGP4 error for {number}: {sorted(set(error.tolist()))}")
    receive_jd, receive_fraction = julian_day_from_utc_ns(receive_ns)
    position_ecef, velocity_ecef = teme_to_ecef(
        position_teme,
        velocity_teme,
        greenwich_mean_sidereal_time_rad(receive_jd, receive_fraction),
    )
    observer = geodetic_to_ecef_km(*SITE)
    enu = ecef_to_enu_matrix(SITE[0], SITE[1])
    azimuth, elevation, slant_range, range_rate = look_angles(
        position_ecef, velocity_ecef, observer, enu
    )
    direction_enu = (position_ecef - observer) @ enu.T
    direction_enu /= np.linalg.norm(direction_enu, axis=1)[:, None]
    return {
        "azimuth_deg": azimuth,
        "elevation_deg": elevation,
        "range_km": slant_range,
        "range_rate_km_s": range_rate,
        "direction_enu": direction_enu,
    }


def phase_deg(direction_enu: np.ndarray, baseline_m: float) -> np.ndarray:
    # Nominal installed baseline: fixture +x is east and RX1 - RX0 is +x.
    return 360.0 * RF_HZ / C_M_S * baseline_m * direction_enu[:, 0]


def wrap_deg(value: np.ndarray) -> np.ndarray:
    return (np.asarray(value) + 180.0) % 360.0 - 180.0


def break_wrapped_line(value: np.ndarray) -> np.ndarray:
    output = np.asarray(value, dtype=float).copy()
    output[1:][np.abs(np.diff(output)) > 180.0] = np.nan
    return output


def central_rate(number: int, elapsed_s: np.ndarray, baseline_m: float) -> np.ndarray:
    step_s = 0.01
    before = phase_deg(states(number, elapsed_s - step_s)["direction_enu"], baseline_m)
    after = phase_deg(states(number, elapsed_s + step_s)["direction_enu"], baseline_m)
    return (after - before) / (2.0 * step_s)


def main() -> None:
    output = Path(__file__).resolve().parent
    fine_time = np.linspace(TIMES_S[0], TIMES_S[-1], 1000)
    fine = {number: states(number, fine_time) for number in CANDIDATES}
    sampled = {number: states(number, TIMES_S) for number in CANDIDATES}
    nominal_baseline = BASELINES_M["illustrative d=50 mm"]

    rows: list[dict[str, object]] = []
    for number in CANDIDATES:
        nominal = phase_deg(sampled[number]["direction_enu"], nominal_baseline)
        rates = central_rate(number, TIMES_S, nominal_baseline)
        for i, visit in enumerate(VISITS):
            rows.append(
                {
                    "candidate": int(number),
                    "visit_index": int(visit),
                    "elapsed_s": float(TIMES_S[i]),
                    "azimuth_deg": float(sampled[number]["azimuth_deg"][i]),
                    "elevation_deg": float(sampled[number]["elevation_deg"][i]),
                    "east_direction_cosine": float(sampled[number]["direction_enu"][i, 0]),
                    "nominal_geometric_phase_deg": float(nominal[i]),
                    "nominal_change_from_first_deg": float(nominal[i] - nominal[0]),
                    "nominal_phase_rate_deg_s": float(rates[i]),
                    "nominal_change_per_120ms_deg": float(rates[i] * 0.120),
                }
            )
    with (output / "geometry-phase-by-dwell.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    leader_phases = {
        label: phase_deg(fine[59925]["direction_enu"], length)
        for label, length in BASELINES_M.items()
    }
    summary = {
        "schema": "org.leo.report.e46-conditional-geometry-phase/v1",
        "session_id": "scan-hop-e46d3aba244cf641",
        "receiver_tracklet_ids": [
            "sha256:e36b7b6bea061125e5a739521fe465b98cebc51539be5158d6da2a4e59d3791b",
            "sha256:78c307f35318463a89d69c38f2b648d13bf892efaf11810f153bc09b8ddf2173",
        ],
        "shared_visits": 106,
        "plotted_visits": VISITS.tolist(),
        "track_start_utc_ns": TRACK_START_UTC_NS,
        "track_duration_s": float(TIMES_S[-1]),
        "rf_hz": RF_HZ,
        "site": {"latitude_deg": SITE[0], "longitude_deg": SITE[1], "altitude_m": SITE[2]},
        "phase_sign": "RX1 minus RX0; phi=(360*f/c)*dot(p_RX1-p_RX0, source_unit)",
        "nominal_pose": "fixture +x east; provisional RX0 negative-x, RX1 positive-x mapping",
        "baselines_m": BASELINES_M,
        "candidates": CANDIDATES,
        "leader_results": {
            "azimuth_start_end_deg": [
                float(sampled[59925]["azimuth_deg"][0]),
                float(sampled[59925]["azimuth_deg"][-1]),
            ],
            "elevation_start_peak_end_deg": [
                float(sampled[59925]["elevation_deg"][0]),
                float(np.max(fine[59925]["elevation_deg"])),
                float(sampled[59925]["elevation_deg"][-1]),
            ],
            "phase_change_deg_by_baseline": {
                label: float(value[-1] - value[0]) for label, value in leader_phases.items()
            },
            "nominal_rate_range_deg_s": [
                float(np.min(central_rate(59925, fine_time, nominal_baseline))),
                float(np.max(central_rate(59925, fine_time, nominal_baseline))),
            ],
        },
        "limits": [
            "NORAD 59925 is a leading Doppler hypothesis, not a claimed identity.",
            "The STL does not measure electrical phase-center offset.",
            "The eastward installed pose and receiver-to-slot mapping are provisional.",
            "Receiver/LNB/channel phase adds an unknown offset, and retunes break observed phase continuity.",
        ],
    }
    (output / "geometry-phase-summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )

    colors = ["#2563eb", "#111827", "#dc2626"]
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 11), constrained_layout=True)

    axis = axes[0]
    axis.plot(fine_time, fine[59925]["elevation_deg"], color="#2563eb", lw=2.2, label="59925 elevation")
    axis.plot(fine_time, fine[59925]["azimuth_deg"], color="#0f766e", lw=2.0, label="59925 azimuth")
    axis.scatter(TIMES_S, sampled[59925]["elevation_deg"], color="#2563eb", s=26, zorder=3)
    axis.set_ylabel("angle (degrees)")
    axis.set_title("Leading candidate crosses near zenith during the shared RF track")
    axis.grid(alpha=0.25)
    axis.legend(ncol=2, frameon=False)

    axis = axes[1]
    for (label, _), color in zip(BASELINES_M.items(), colors, strict=True):
        value = leader_phases[label] - leader_phases[label][0]
        axis.plot(fine_time, value, color=color, lw=2.1, label=f"59925: {label}")
    runner = phase_deg(fine[60188]["direction_enu"], nominal_baseline)
    axis.plot(
        fine_time, runner - runner[0], color="#7c3aed", lw=1.8, ls="--",
        label="60188 runner: illustrative d=50 mm",
    )
    for t in TIMES_S:
        axis.axvline(t, color="#94a3b8", lw=0.45, alpha=0.45)
    axis.set_ylabel("unwrapped geometric change (degrees)")
    axis.set_title("Conditional RX1-minus-RX0 geometric phase change")
    axis.grid(alpha=0.25)
    axis.legend(ncol=2, fontsize=9, frameon=False)

    axis = axes[2]
    for (label, baseline), color in zip(BASELINES_M.items(), colors, strict=True):
        rate = central_rate(59925, fine_time, baseline)
        axis.plot(fine_time, 0.120 * rate, color=color, lw=2.1, label=label)
    runner_rate = central_rate(60188, fine_time, nominal_baseline)
    axis.plot(fine_time, 0.120 * runner_rate, color="#7c3aed", lw=1.8, ls="--", label="60188 runner, d=50 mm")
    axis.scatter(
        TIMES_S,
        0.120 * central_rate(59925, TIMES_S, nominal_baseline),
        color="#111827", s=25, zorder=3, label="selected dwell starts",
    )
    axis.set_xlabel("seconds since visit 376 (2026-09-21 12:37:04.176 UTC)")
    axis.set_ylabel("geometric change per 120 ms dwell (degrees)")
    axis.set_title("Expected orbital phase motion inside each dwell")
    axis.grid(alpha=0.25)
    axis.legend(ncol=2, fontsize=9, frameon=False)

    fig.suptitle(
        "scan-hop-e46d3aba244cf641 — conditional LT3D-001A geometry simulation\n"
        "nominal baseline points east; observed receiver phase also contains an unknown path offset",
        fontsize=14,
    )
    fig.savefig(output / "conditional-geometry-phase.png", dpi=180)

    wrapped_fig, wrapped_axes = plt.subplots(2, 1, figsize=(11.5, 8.5), constrained_layout=True)
    axis = wrapped_axes[0]
    for (label, _), color in zip(BASELINES_M.items(), colors, strict=True):
        wrapped = wrap_deg(leader_phases[label])
        axis.plot(fine_time, break_wrapped_line(wrapped), color=color, lw=2.0, label=label)
        dwell_phase = wrap_deg(phase_deg(sampled[59925]["direction_enu"], BASELINES_M[label]))
        axis.scatter(TIMES_S, dwell_phase, color=color, s=20, zorder=3)
    axis.set_ylim(-190, 190)
    axis.set_yticks([-180, -90, 0, 90, 180])
    axis.set_ylabel("wrapped geometric phase (degrees)")
    axis.set_title("Continuous geometric term, wrapped to [−180°, +180°)")
    axis.grid(alpha=0.25)
    axis.legend(ncol=3, fontsize=9, frameon=False)

    axis = wrapped_axes[1]
    local_ms = np.linspace(0.0, 120.0, 241)
    cmap = plt.get_cmap("viridis")
    normalization = plt.Normalize(float(TIMES_S[0]), float(TIMES_S[-1]))
    for visit, start_s in zip(VISITS, TIMES_S, strict=True):
        local_time = start_s + local_ms / 1000.0
        local_phase = phase_deg(states(59925, local_time)["direction_enu"], nominal_baseline)
        local_change = local_phase - local_phase[0]
        axis.plot(
            local_ms,
            local_change,
            color=cmap(normalization(float(start_s))),
            lw=1.9,
        )
    axis.set_xlim(0, 120)
    axis.set_ylim(0, 2.25)
    axis.set_xlabel("time within each 120 ms dwell (ms)")
    axis.set_ylabel("change from dwell start (degrees)")
    axis.set_title("Magnified within-dwell motion after removing each wrapped start phase")
    axis.grid(alpha=0.25)
    scalar = plt.cm.ScalarMappable(norm=normalization, cmap=cmap)
    colorbar = wrapped_fig.colorbar(scalar, ax=axis, pad=0.02)
    colorbar.set_label("seconds since visit 376")

    wrapped_fig.suptitle(
        "Wrapped phase most directly comparable to a receiver output\n"
        "conditional on candidate 59925, eastward baseline and zero added path-phase offset",
        fontsize=14,
    )
    wrapped_fig.savefig(output / "conditional-geometry-phase-wrapped.png", dpi=180)


if __name__ == "__main__":
    main()
