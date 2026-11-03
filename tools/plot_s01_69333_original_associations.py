"""Show all ten 69333 nominees, split by their pre-retrospective association."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import ROOT, load_study
from investigate_s01_ch4_t001 import OUTPUT, PRIOR, residual_rows, statistics
from plot_s01_phase_sensitivity import RAW

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import profile_phases

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def run():
    study, *_ = load_study("DSX01-S01", True)
    fit = json.loads((PRIOR / "fitted_c/fit_cap_2.7.json").read_text())
    association = json.loads((PRIOR / "fitted_c/association_cap_2.7.json").read_text())
    rows = {r["component"]: r for r in association["association"]["rows"]
            if r["candidate_norad"] == 69333}
    tracks = [t for t in study.tracks if t["key"] in rows]
    raw = {r["observation_id"]: r for line in RAW.read_text().splitlines()
           if (r := json.loads(line))["source_id"] == "S01"}
    assert len(tracks) == 10 and sum(len(t["times"]) for t in tracks) == 264
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    selected = np.flatnonzero(study.sky["norad"] == 69333)
    sky = {k: study.sky[k][selected] for k in ("position_km", "velocity_km_s")}
    sky["time_s"] = study.sky["time_s"]
    phase = np.array([fit["phases_s"][selected[0]]])
    geometry = prepare_phase_geometry(sky, times, phase)
    f, e, h = phase_linear_frequency(geometry, fit["latitude_deg"], fit["longitude_deg"])
    stats = statistics(tracks, times, f, e, h, phase)
    terms = profile_phases(stats, np.array(fit["beta"]), phase)
    residuals = {r["component"]: r for r in residual_rows(
        tracks, times, f, terms, np.array(fit["beta"]), stats["component_visible"])}
    colors = {t["key"]: plt.get_cmap("tab10")(i) for i, t in enumerate(tracks)}
    limits = (min(times) - 3, max(times) + 3)
    native_values = [raw[oid]["measured_cfo_hz"] / 1000 for t in tracks
                     for oid in t["observation_ids"]]
    all_residual = np.concatenate([r["residual_hz"] for r in residuals.values()])
    summary = []
    for compatible, name in [(True, "associated"), (False, "unassociated")]:
        own = [t for t in tracks if rows[t["key"]]["compatible"] == compatible]
        assert (len(own), sum(len(t["times"]) for t in own)) == (
            (4, 65) if compatible else (6, 199))
        fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True, layout="constrained",
                                 gridspec_kw=dict(height_ratios=[1.25, 1]))
        handles = []
        for t in own:
            key = t["key"]
            c = colors[key]
            native = {}
            for oid, time, value in zip(t["observation_ids"], t["times"], t["values"],
                                        strict=True):
                point = raw[oid]
                assert (point["receiver"], point["channel"], point["time_s"]) == (
                    t["receiver"], t["channel"], time)
                alias = (value - point["measured_cfo_hz"]) / (1 / 4.4e-6)
                assert abs(alias - round(alias)) < 1e-8
                native[oid] = round(alias)
            axes[0].scatter(t["times"], [raw[oid]["measured_cfo_hz"] / 1000
                                        for oid in t["observation_ids"]],
                            color=c, s=24, alpha=0.85, zorder=3)
            for piece in t["pieces"]:
                ids = sorted(piece["observation_ids"], key=lambda oid: raw[oid]["time_s"])
                # Keep genuine sampling gaps visible; never connect an alias wrap.
                for left, right in zip(ids[:-1], ids[1:], strict=True):
                    start, stop = raw[left]["time_s"], raw[right]["time_s"]
                    if stop - start > 8 or native[left] != native[right]:
                        continue
                    grid = np.linspace(start, stop, 12)
                    x = (grid - piece["reference_time_s"]) / piece["time_scale_s"]
                    values = np.polynomial.polynomial.polyval(x, piece["coefficients_hz"])
                    axes[0].plot(grid, (values - native[left] / 4.4e-6) / 1000,
                                 color=c, linewidth=1.8, alpha=0.9)
            r = residuals[key]
            assert abs(r["rms_hz"] - rows[key]["rms_hz"]) < 0.01
            axes[1].plot(t["times"], r["residual_hz"], "o-", color=c, markersize=4,
                         linewidth=1.3, alpha=0.85)
            short = key.replace("S01-RX1-", "")
            handles.append(Line2D([], [], color=c, marker="o", markersize=4,
                                  label=f"{short} · {len(t['times'])} points"))
            summary.append(dict(component=key, originally_associated=compatible,
                                points=len(t["times"]), color=list(c),
                                current_physical_rms_hz=r["rms_hz"]))
        axes[0].set(ylabel="Measured GLRT CFO (kHz)",
                    ylim=(min(native_values) - 5, max(native_values) + 5),
                    title="GLRT points and graph polynomial fits; native CFO branches")
        axes[1].set(ylabel="Residual CFO (Hz)", xlabel="Seconds from S01 scan start",
                    ylim=(min(all_residual) - 50, max(all_residual) + 50),
                    title="Residual to original causal 69333 model; receiver/band drift included")
        axes[1].axhline(0, color="black", linewidth=0.8)
        for ax in axes:
            ax.set_xlim(limits)
            ax.grid(alpha=0.2)
        fig.legend(handles=handles, loc="outside lower center", ncol=3, fontsize=9)
        label = "Originally associated" if compatible else "Originally unassociated"
        fig.suptitle(f"DSX01 S01 · NORAD 69333 / STARLINK-37818 · {label}\n"
                     f"{len(own)} graph fragments · {sum(len(t['times']) for t in own)} "
                     "GLRT points · all RX1 · before the later-TLE test", fontsize=14)
        fig.savefig(OUTPUT / f"69333_originally_{name}.png", dpi=180)
        plt.close(fig)
    write(OUTPUT / "69333_original_association_plot_counts.json", dict(
        association_source=str((PRIOR / "fitted_c/association_cap_2.7.json").relative_to(ROOT)),
        graph_partition_preserved=True, no_new_calibration=True,
        residuals_use_original_causal_phase_and_hardware=True,
        per_fragment_constant_profiled_but_no_extra_rate_fitted=True,
        track_colors_unique_across_both_figures=True, rows=summary))


if __name__ == "__main__":
    run()
