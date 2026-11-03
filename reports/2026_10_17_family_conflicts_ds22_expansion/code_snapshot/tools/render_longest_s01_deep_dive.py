"""Visual proof and accounting for the longest unassociated S01 curve."""

import json

import analyze_dsx01_fixed_site as matching
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import write
from deep_dive_longest_unassociated_s01 import CURRENT, OUTPUT, TARGET
from inventory_clipped_phase_cohort import load_study

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)


def read(path):
    return json.loads(path.read_text())


def run():
    study, _, _, _, _ = load_study("DSX01-S01", True)
    before = read(CURRENT / "fitted_c/fit.json")
    after = read(OUTPUT / "fitted_c/curved_consensus/fit.json")
    association = read(OUTPUT / "fitted_c/curved_consensus/association.json")
    old = read(CURRENT / "fitted_c/association.json")
    bykey = {t["key"]: t for t in study.tracks}
    target = bykey[TARGET]
    oldrows = {r["component"]: r for r in old["association"]["rows"]}
    gains = [
        r
        for r in association["association"]["rows"]
        if r["compatible"] and not oldrows[r["component"]]["compatible"]
    ]
    j = int(np.flatnonzero(study.sky["norad"] == 63474)[0])
    sky = {key: study.sky[key][[j]] for key in ["position_km", "velocity_km_s"]}
    sky["time_s"] = study.sky["time_s"]

    def details(tracks, fit):
        times = np.unique(np.concatenate([t["times"] for t in tracks]))
        geometry = prepare_phase_geometry(sky, times, np.array([fit["phases_s"][j]]))
        f, e, _ = phase_linear_frequency(geometry, fit["latitude_deg"], fit["longitude_deg"])
        stats = matching.statistics(
            [(t["key"], [t]) for t in tracks],
            dict(time_s=times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for t in tracks},
        )
        terms = profile_component_bias(stats, np.array(fit["beta"]), bias_sigma_hz=1000)
        result = {}
        beta = np.array(fit["beta"])
        for i, t in enumerate(tracks):
            ix = np.searchsorted(times, t["times"])
            g = matching.group(t)
            q = t["rf_hz"] / 11.5e9
            hw = (
                beta[g]
                + beta[g + 4] * (t["times"] - 150) / 150
                + beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            )
            bias = float(terms.bias_hz[i, 0])
            alias = int(terms.aliases[i, 0])
            prediction = q * f[0, ix] + hw + bias - alias * matching.PERIOD
            residual = t["values"] - prediction
            x = t["times"] - t["times"].mean()
            slope = float(x @ (residual - residual.mean()) / (x @ x))
            result[t["key"]] = dict(
                prediction_hz=prediction,
                residual_hz=residual,
                bias_hz=bias,
                native_alias=alias,
                rms_hz=float(np.sqrt(np.mean(residual**2))),
                slope_hz_s=slope,
                affine_diagnostic_rms_hz=float(
                    np.sqrt(np.mean((residual - residual.mean() - slope * x) ** 2))
                ),
                diagnostics=matching.noise_screen(residual, t["times"]),
                normalized_observed_hz=(t["values"] + alias * matching.PERIOD - hw - bias) / q,
            )
        return result, times, f[0]

    prior, _, _ = details([target], before)
    new, _, _ = details([target], after)
    a, b = prior[TARGET], new[TARGET]
    piece = target["pieces"][0]
    x = (target["times"] - piece["reference_time_s"]) / piece["time_scale_s"]
    design = np.polynomial.polynomial.polyvander(x, piece["degree"])
    q, _ = np.linalg.qr(design)
    leverage = np.sum(q * q, axis=1)
    polynomial = design @ np.array(piece["coefficients_hz"])
    polynomial_residual = target["values"] - polynomial
    selected = read(OUTPUT / "fitted_c/curved_consensus/selected_phase.json")
    phases = read(OUTPUT / "fitted_c/curved_consensus/phase_profile.json")
    colors = ["#21905c", "#c63b32", "#2878b5", "#b27b00"]
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), layout="constrained")
    ax = axes[0, 0]
    ax.scatter(
        target["times"], target["values"] / 1000, s=18, color="#222222", label="All 71 GLRT points"
    )
    ax.plot(
        target["times"],
        a["prediction_hz"] / 1000,
        "--",
        color="#c63b32",
        label="Old phase −0.616 s; RMS 1,556 Hz",
    )
    ax.plot(
        target["times"],
        b["prediction_hz"] / 1000,
        color="#2878b5",
        label="Common phase −2.70 s; RMS 132 Hz",
    )
    ax.set(title="Longest curve: RX1 CH6 T001", ylabel="Unwrapped GLRT CFO (kHz)")
    ax.legend(fontsize=8)
    ax = axes[0, 1]
    ax.scatter(
        target["times"],
        polynomial_residual,
        s=15,
        color="#a0a0a0",
        label="Empirical quartic residual · 131 Hz",
    )
    ax.scatter(
        target["times"],
        b["residual_hz"],
        s=16,
        color="#2878b5",
        label="STARLINK-33735 residual · 132 Hz",
    )
    ax.axhline(0, color="black", lw=0.6)
    ax.set(
        ylim=(-450, 450),
        ylabel="Residual (Hz)",
        title="All original points; no fitted slope or point removal",
    )
    ax.legend(fontsize=8)
    ax = axes[1, 0]
    for index, r in enumerate(selected["rows"]):
        key = r["component"]
        curve = [next(v for v in row["rows"] if v["component"] == key)["rms_hz"] for row in phases]
        ax.semilogy(
            [p["phase_s"] for p in phases],
            curve,
            color=colors[index],
            label=key.replace("S01-", ""),
        )
    bound = study.bounds[j]
    ax.axvspan(-bound, bound, color="#b0b0b0", alpha=0.25, label="Old phase search box")
    ax.axvline(after["phases_s"][j], color="black", lw=0.8, ls="--")
    ax.set(
        xlim=(-4, 1),
        ylim=(75, 12000),
        xlabel="Orbital phase parameter (s)",
        ylabel="Residual RMS (Hz)",
        title="Three curves agree outside the old phase box",
    )
    ax.legend(fontsize=7)
    ax = axes[1, 1]
    for index, r in enumerate(selected["rows"]):
        t = bykey[r["component"]]
        text = r["component"].replace("S01-", "") + (
            " · remains rejected" if not r["passing"] else ""
        )
        ax.plot(t["times"], r["residual_hz"], ".-", ms=3, lw=0.7, color=colors[index], label=text)
    ax.axhline(0, color="black", lw=0.6)
    ax.set(
        ylabel="Residual after component constant (Hz)",
        title="The fourth nominee must not veto the coherent three",
    )
    ax.legend(fontsize=7)
    for ax in axes.flat:
        ax.grid(alpha=0.2)
        if ax is not axes[1, 0]:
            ax.set_xlabel("Seconds from scan start")
    fig.suptitle(
        "DSX01 S01 · STARLINK-33735 / NORAD 63474\n"
        "Fixed supplied GPS; hardware frozen; phase learned from measured-curved tracks only",
        fontsize=14,
    )
    fig.savefig(OUTPUT / "longest_track_diagnosis.png", dpi=160)
    plt.close(fig)

    tracks = [bykey[r["component"]] for r in gains]
    recovered, times, frequency = details(tracks, after)
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), layout="constrained")
    for i, r in enumerate(gains):
        t = bykey[r["component"]]
        d = recovered[r["component"]]
        color = plt.get_cmap("tab10")(i)
        label = r["component"].replace("S01-", "") + (
            " · curved anchor" if r["active_curvature"] else " · post-fit association"
        )
        axes[0].scatter(
            t["times"], d["normalized_observed_hz"] / 1000, s=13, color=color, label=label
        )
        axes[1].scatter(t["times"], d["residual_hz"], s=13, color=color)
    axes[0].plot(times, frequency / 1000, color="black", lw=1.0, label="One physical Doppler curve")
    axes[0].set(ylabel="At 11.5 GHz after hardware, alias and constant correction (kHz)")
    axes[0].legend(fontsize=7, ncol=2)
    axes[1].axhline(0, color="black", lw=0.6)
    axes[1].set(ylabel="Native-Hz residual", ylim=(-600, 600))
    for ax in axes:
        ax.set_xlabel("Seconds from scan start")
        ax.grid(alpha=0.2)
    fig.suptitle(
        "One corrected satellite phase recovers 231 GLRT points in eight fragments\n"
        "Three curved anchors calibrate; five shorter fragments associate afterward",
        fontsize=13,
    )
    fig.savefig(OUTPUT / "recovered_family.png", dpi=160)
    plt.close(fig)

    unresolved = [r for r in oldrows.values() if not r["compatible"]]
    reasons = {
        name: dict(fragments=len(subset), points=sum(r["points"] for r in subset))
        for name, subset in [
            (
                "no_candidate_passes_current_frequency_gates",
                [r for r in unresolved if r["candidates_passing_all_frequency_gates"] == 0],
            ),
            (
                "chosen_nomination_structured_residual",
                [r for r in unresolved if not r["residual_diagnostics"]["noise_screen_pass"]],
            ),
            (
                "chosen_nomination_bias_over_3000",
                [r for r in unresolved if abs(r["bias_hz"]) > 3000],
            ),
            ("chosen_nomination_rms_over_450", [r for r in unresolved if r["rms_hz"] > 450]),
            (
                "passes_frequency_but_lacks_curved_satellite_support",
                [r for r in unresolved if r["candidates_passing_all_frequency_gates"] > 0],
            ),
        ]
    }
    write(
        OUTPUT / "diagnosis_metrics.json",
        dict(
            target_before=a,
            target_after=b,
            polynomial=dict(
                degree=piece["degree"],
                points=len(x),
                rms_hz=float(np.sqrt(np.mean(polynomial_residual**2))),
                maximum_point_leverage=float(leverage.max()),
                endpoint_leverage=float(leverage[-1]),
                diagnostics=matching.noise_screen(polynomial_residual, target["times"]),
            ),
            old_unassociated_reasons_nonexclusive=reasons,
            recovered_family=gains,
        ),
    )
    print(
        json.dumps(
            dict(
                before_rms=a["rms_hz"],
                before_slope=a["slope_hz_s"],
                before_affine_rms=a["affine_diagnostic_rms_hz"],
                after_rms=b["rms_hz"],
                after_slope=b["slope_hz_s"],
                maximum_polynomial_leverage=float(leverage.max()),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    run()
