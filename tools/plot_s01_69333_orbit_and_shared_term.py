"""Decompose the causal orbit prediction and the one-coefficient shared term."""

import json

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import load_study
from investigate_s01_ch4_t001 import OUTPUT, PRIOR

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def run():
    study, *_ = load_study("DSX01-S01", True)
    fit = json.loads((PRIOR / "fitted_c/fit_cap_2.7.json").read_text())
    saved = json.loads((OUTPUT / "69333_shared_rate_plot_results.json").read_text())
    rows = {r["component"]: r for r in saved["rows"]}
    tracks = [t for t in study.tracks if t["key"] in rows]
    colors = {t["key"]: plt.get_cmap("tab10")(i) for i, t in enumerate(tracks)}
    beta = np.array(fit["beta"])
    rate, phase = saved["shared_rate_hz_s_at_11_5ghz"], saved["shared_phase_s"]
    selected = np.flatnonzero(study.sky["norad"] == 69333)
    sky = {k: study.sky[k][selected] for k in ("position_km", "velocity_km_s")}
    sky["time_s"] = study.sky["time_s"]
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    dense = np.linspace(min(times) - 2, max(times) + 2, 1500)

    def orbit(grid, phase_s):
        geom = prepare_phase_geometry(sky, grid, np.array([phase_s]))
        f, *_ = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
        return f[0]

    nominal_dense = orbit(dense, 0)
    aligned_dense = orbit(dense, phase)
    aligned_points = orbit(times, phase)
    normalized = {}
    for t in tracks:
        g = matching.group(t)
        hardware = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
        hardware += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
        q = t["rf_hz"] / 11.5e9
        f = aligned_points[np.searchsorted(times, t["times"])]
        observed = t["values"] - hardware
        alias = round(float(np.mean(q * f - observed)) / matching.PERIOD)
        y = (observed + alias * matching.PERIOD - rows[t["key"]]["bias_hz"]) / q
        residual = y - f - rate * (t["times"] - 65)
        np.testing.assert_allclose(residual, np.array(rows[t["key"]]["residual_hz"]) / q,
                                   atol=1e-6)
        normalized[t["key"]] = dict(values_hz=y, orbit_hz=f, residual_hz=residual)
    for mode in ("all", "associated", "unassociated"):
        own = [t for t in tracks if mode == "all"
               or rows[t["key"]]["originally_associated"] == (mode == "associated")]
        fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True, layout="constrained")
        axes[0].plot(dense, nominal_dense / 1000, color="#777777", ls=":", lw=2.2,
                     label="Causal TLE orbit, phase = 0")
        axes[0].plot(dense, aligned_dense / 1000, color="black", ls="--", lw=1.6,
                     label=f"Same orbit, fitted phase {phase:+.2f} s")
        axes[0].plot(dense, (aligned_dense + rate * (dense - 65)) / 1000,
                     color="black", lw=1.6, label="Phase-aligned orbit + shared linear term")
        axes[1].plot(dense, rate * (dense - 65), color="black", lw=2,
                     label=f"One coefficient: Δf(t) = {rate:.3f} × (t − 65) Hz")
        axes[2].axhline(0, color="black", lw=1)
        handles = []
        for t in own:
            key, color = t["key"], colors[t["key"]]
            data = normalized[key]
            axes[0].scatter(t["times"], data["values_hz"] / 1000, color=color, s=16,
                            alpha=0.8, zorder=4)
            axes[1].plot(t["times"], data["values_hz"] - data["orbit_hz"], ".-",
                         color=color, ms=5, lw=0.8, alpha=0.85)
            axes[2].plot(t["times"], data["residual_hz"], ".-", color=color,
                         ms=5, lw=0.8, alpha=0.85)
            handles.append(Line2D([], [], color=color, marker="o", markersize=4,
                                  label=f"{key.replace('S01-RX1-', '')} · {len(t['times'])} pts"))
        axes[0].set(title="Orbit-expected Doppler and calibrated GLRT measurements",
                    ylabel="Doppler at 11.5 GHz (kHz)")
        axes[1].set(title="Measurements minus phase-aligned orbit; shared straight-line correction",
                    ylabel="Correction at 11.5 GHz (Hz)", ylim=(-520, 1000))
        axes[2].set(title="Residual after orbit + shared line",
                    ylabel="Residual at 11.5 GHz (Hz)", ylim=(-450, 650),
                    xlabel="Seconds from S01 scan start")
        axes[0].legend(loc="upper right", fontsize=8)
        axes[1].legend(loc="upper left", fontsize=8)
        for ax in axes:
            ax.set_xlim(min(dense), max(dense))
            ax.grid(alpha=0.2)
        title = "All 10 tracks" if mode == "all" else f"Originally {mode} tracks"
        fig.suptitle("DSX01 S01 · NORAD 69333 / STARLINK-37818 · " + title + "\n"
                     "1 added slope; existing shared phase and track constants refitted\n"
                     "GLRT dots: hardware, native aliases and track constants removed; "
                     "RF-normalized; shared slope remains in dots", fontsize=12)
        fig.legend(handles=handles, loc="outside lower center", ncol=5 if mode == "all" else 3,
                   fontsize=8)
        fig.savefig(OUTPUT / f"69333_orbit_shared_term_{mode}.png", dpi=170)
        plt.close(fig)
    write(OUTPUT / "69333_orbit_shared_term_decomposition.json", dict(
        new_shared_coefficients=1, slope_hz_s_at_11_5ghz=rate,
        fixed_reference_time_s=65, shared_intercept_added=False,
        existing_shared_phase_refitted_s=phase, curved_track_constants_refitted=9,
        total_curved_family_fit_parameters=11,
        linear_track_extra_constant_for_display_only=1,
        receiver_band_coefficients_fixed=True,
        raw_points_unchanged=True, empirical_polynomial_not_used_for_orbit_curve=True,
        normalized_data_still_include_shared_slope=True,
        nominal_and_phase_shifted_orbit_curves_from_causal_tle=True,
        zero_mean_residuals_use_existing_fitted_track_constants=True,
        data_match_saved_residuals_to_1e_6hz=True,
    ))


if __name__ == "__main__":
    run()
