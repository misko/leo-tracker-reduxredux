"""Show the shared-rate diagnostic on the original two 69333 track groups."""

import json

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import load_study
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
    assoc = json.loads((PRIOR / "fitted_c/association_cap_2.7.json").read_text())
    rows = {r["component"]: r for r in assoc["association"]["rows"]
            if r["candidate_norad"] == 69333}
    tracks = [t for t in study.tracks if t["key"] in rows]
    raw = {r["observation_id"]: r for line in RAW.read_text().splitlines()
           if (r := json.loads(line))["source_id"] == "S01"}
    fitted = json.loads((OUTPUT / "fitted_c/shared_shape_diagnostics.json").read_text())
    state = fitted["all_curves/shared_linear_rate"]
    rate = state["shared_parameters"]["rate"]
    phase = np.array([state["phase_s"]])
    curved = {r["component"]: r for r in state["rows"]}
    assert len(curved) == 9 and sum(r["points"] for r in curved.values()) == 254
    assert all(k in study.curved_keys for k in curved)
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    selected = np.flatnonzero(study.sky["norad"] == 69333)
    sky = {k: study.sky[k][selected] for k in ("position_km", "velocity_km_s")}
    sky["time_s"] = study.sky["time_s"]
    old_phase = np.array([fit["phases_s"][selected[0]]])
    geom = prepare_phase_geometry(sky, times, old_phase)
    f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
    stats = statistics(tracks, times, f, e, h, old_phase)
    terms = profile_phases(stats, np.array(fit["beta"]), old_phase)
    before = {r["component"]: r for r in residual_rows(
        tracks, times, f, terms, np.array(fit["beta"]), stats["component_visible"])}
    geom = prepare_phase_geometry(sky, times, phase)
    f, _, _ = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
    after = {}
    beta = np.array(fit["beta"])
    for t in tracks:
        g = matching.group(t)
        hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
        hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
        q = t["rf_hz"] / 11.5e9
        predicted = q * f[0, np.searchsorted(times, t["times"])]
        observed = t["values"] - hw
        alias = round(float(np.mean(predicted - observed)) / matching.PERIOD)
        residual = observed + alias * matching.PERIOD - predicted - q * rate * (t["times"] - 65)
        bias = float(np.mean(residual))
        residual -= bias
        diagnostics = matching.noise_screen(residual, t["times"])
        rms = float(np.sqrt(np.mean(residual**2)))
        after[t["key"]] = dict(
            residual_hz=residual, rms_hz=rms, bias_hz=bias, diagnostics=diagnostics,
            passing=bool(rms <= 450 and abs(bias) <= 3000 and diagnostics["noise_screen_pass"]),
            used_for_shared_fit=t["key"] in curved,
        )
        if t["key"] in curved:
            assert np.max(abs(residual - curved[t["key"]]["residual_hz"])) < 1e-6
            np.testing.assert_allclose(rms, curved[t["key"]]["rms_hz"], atol=1e-6)
    colors = {t["key"]: plt.get_cmap("tab10")(i) for i, t in enumerate(tracks)}
    plotted = []
    native_y = [raw[oid]["measured_cfo_hz"] / 1000 for t in tracks for oid in t["observation_ids"]]
    all_residuals = np.concatenate([r["residual_hz"] for r in [*before.values(), *after.values()]])
    ylim = (min(all_residuals) - 40, max(all_residuals) + 40)
    for compatible, name in ((True, "associated"), (False, "unassociated")):
        own = [t for t in tracks if rows[t["key"]]["compatible"] == compatible]
        fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True, layout="constrained")
        handles = []
        for t in own:
            key, c = t["key"], colors[t["key"]]
            actual = [raw[oid]["measured_cfo_hz"] / 1000 for oid in t["observation_ids"]]
            axes[0].scatter(t["times"], actual, color=c, s=19, zorder=3)
            axes[0].plot(t["times"], np.array(actual) - after[key]["residual_hz"] / 1000,
                         color=c, linewidth=1.6)
            axes[1].plot(t["times"], before[key]["residual_hz"], "o-", color=c,
                         markersize=3.5, linewidth=1.2)
            axes[2].plot(t["times"], after[key]["residual_hz"], "o-", color=c,
                         markersize=3.5, linewidth=1.2)
            rms_label = f"{before[key]['rms_hz']:.0f} → {after[key]['rms_hz']:.0f} Hz"
            handles.append(Line2D([], [], color=c, marker="o", markersize=4,
                                  label=f"{key.replace('S01-RX1-', '')} · {rms_label}"))
            plotted.append(dict(component=key, originally_associated=compatible,
                                points=len(t["times"]), rms_before_hz=before[key]["rms_hz"],
                                rms_after_hz=after[key]["rms_hz"], **after[key]))
        axes[0].set(title="Measured GLRT points + physical prediction with the shared term",
                    ylabel="Measured CFO (kHz)", ylim=(min(native_y) - 5, max(native_y) + 5))
        axes[1].set(title="Before: existing receiver/band drift and original satellite phase",
                    ylabel="Residual (Hz)", ylim=ylim)
        axes[2].set(title="After: one extra shared rate + one shared phase; constants per track",
                    ylabel="Residual (Hz)", xlabel="Seconds from S01 scan start", ylim=ylim)
        for ax in axes[1:]:
            ax.axhline(0, color="black", linewidth=0.8)
        for ax in axes:
            ax.set_xlim(min(times) - 3, max(times) + 3)
            ax.grid(alpha=0.2)
        label = "Originally associated" if compatible else "Originally unassociated"
        fig.suptitle(f"DSX01 S01 · NORAD 69333 · {label}\n"
                     f"Extra shared rate {rate:+.2f} Hz/s at 11.5 GHz · phase {phase[0]:+.2f} s\n"
                     "Causal TLE; receiver/band calibration fixed; fit uses only 9 curved tracks",
                     fontsize=13)
        fig.legend(handles=handles, loc="outside lower center", ncol=3, fontsize=9)
        fig.savefig(OUTPUT / f"69333_shared_rate_{name}.png", dpi=170)
        plt.close(fig)
    curved_tracks = [t for t in tracks if t["key"] in curved]
    pooled_t = np.concatenate([t["times"] for t in curved_tracks])
    pooled_r = np.concatenate([after[t["key"]]["residual_hz"] for t in curved_tracks])
    order = np.argsort(pooled_t, kind="stable")
    pooled_noise = matching.noise_screen(pooled_r[order], pooled_t[order])
    write(OUTPUT / "69333_shared_rate_plot_results.json", dict(
        shared_rate_hz_s_at_11_5ghz=rate, shared_phase_s=float(phase[0]),
        term="(track_rf_hz/11.5e9)*rate_hz_s*(time_s-65)",
        receiver_band_calibration_fixed=True, causal_tle=True,
        curved_fitting_tracks=9, curved_fitting_points=254,
        linear_tracks_do_not_fit_or_rank_shared_term=True,
        per_track_constants_reprofiled=True, existing_original_labels_preserved_in_plot_groups=True,
        pooled_curved_diagnostics=pooled_noise,
        no_production_association_changed=True, rows=plotted,
    ))
    print(json.dumps(dict(rate=rate, phase_s=float(phase[0]),
                          passing_tracks=sum(r["passing"] for r in plotted),
                          passing_points=sum(r["points"] for r in plotted if r["passing"]),
                          pooled_curved_diagnostics=pooled_noise,
                          rms=[(r["component"], round(r["rms_before_hz"], 1),
                                round(r["rms_after_hz"], 1)) for r in plotted])), flush=True)


if __name__ == "__main__":
    run()
