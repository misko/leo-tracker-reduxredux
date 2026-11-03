"""Figures from frozen DS23 diagnostic results; no inference or model selection."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/2026_10_18_ds23_adaptive_failures"
SOURCE = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"
GENUINE = OUT / "genuine_causal_prior"
CASES = ("DS23-0342", "DS23-0039")


def read(path):
    return json.loads(path.read_text())


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)


def comparisons():
    fig, axes = plt.subplots(1, 2, figsize=(15, 5), sharey=True)
    for ax, case in zip(axes, CASES, strict=True):
        repairs = read(GENUINE / case / "repairs.json")["results"]
        audit = read(OUT / case / "audit.json")["arms"]
        names = ["Published\nbaseline", "Genuine prior;\nreject failed track",
                 "Also widen phase\nto 3 s (sensitivity)", "Age/disagreement\nphase prior"]
        for arm, offset, color, label in (("c0", -.18, "tab:blue", "c = 0"),
                                          ("fitted_c", .18, "tab:orange", "Fitted c")):
            vals = [audit[arm]["error_km"]]
            for variant in ("remove_failed", "phase3_quality", "causal_phase_quality"):
                vals.append(next(r["error_km"] for r in repairs
                                 if r["variant"] == variant and r["arm"] == arm))
            if case == "DS23-0342":
                trim = read(GENUINE / case / "trim_failed.json")["results"][0]
                vals.append(next(r["error_km"] for r in trim["refits"]
                                 if r["kind"] == "causal" and r["arm"] == arm))
                if arm == "c0":
                    names.append("Retain split suffix;\nage/disagreement prior")
            bars = ax.bar(np.arange(len(vals))+offset, vals, width=.34, label=label, color=color)
            ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
        ax.set_xticks(np.arange(len(names)), names, rotation=23, ha="right", fontsize=8)
        ax.axhline(1, ls="--", c=".5", lw=1)
        ax.set(title=case, ylabel="Position error (km)", ylim=(0, 5.7))
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
        ax.legend()
    fig.suptitle("Controlled interventions: GPS evaluates fits; it does not select masks or priors")
    save(fig, "interventions.png")


def influence():
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for ax, case in zip(axes, CASES, strict=True):
        baseline = read(OUT / case / "audit.json")["arms"]["c0"]["error_km"]
        rows = [r for r in read(OUT / case / "family_influence.json")["results"]
                if r["arm"] == "c0"]
        rows.sort(key=lambda r: r["error_km"])
        ax.barh([r["target"] for r in rows], [r["error_km"] for r in rows],
                color=["crimson" if r["target"] == "68214" else "steelblue" for r in rows])
        ax.invert_yaxis()
        ax.axvline(baseline, ls="--", c="black", label="Full baseline")
        ax.set(title=case, xlabel="Position error after deleting one family (km)", ylabel="NORAD")
        ax.legend()
        ax.grid(axis="x", alpha=.2)
    fig.suptitle("Influence diagnostics: original prior support and phase tangent retained, c=0")
    save(fig, "family_influence.png")


def bridge():
    case = "DS23-0342"
    audit = read(OUT / case / "audit.json")["arms"]["c0"]
    trim = read(GENUINE / case / "trim_failed.json")["results"][0]
    prefix = read(GENUINE / case / "prefix_validation.json")["results"][0]
    tracks = read(SOURCE / case / "tracks.json")
    raw = {r["observation_id"]: r for r in read(SOURCE / case / "observations.json")}
    t = next(t for t in tracks if t["key"] == trim["component"])
    times, y = np.array(t["times"]), np.array([raw[k]["measured_cfo_hz"]
                                              for k in t["observation_ids"]])
    k = next(k for k, a in enumerate(audit["track_audit"]) if a["component"] == t["key"])
    start, stop = audit["slices"][k]
    old_residual = np.array(audit["conditional_residual_hz"])[start:stop]
    n = prefix["prefix_points"]
    first = np.array(prefix["candidates"][0]["residual_hz"])
    last = np.array(prefix["retained_suffix_residual_hz"])
    piece = t["pieces"][0]
    poly = np.polynomial.legendre.legval(
        (times-piece["reference_time_s"])/piece["time_scale_s"], piece["coefficients_hz"])
    poly -= np.array(t["values"])-y
    fig, axes = plt.subplots(3, 1, figsize=(13, 11), sharex=True)
    axes[0].plot(times, poly/1000, c=".5", lw=1, label="Graph's single degree-4 polynomial")
    axes[0].scatter(times, y/1000, c="black", s=20, label="All 48 original GLRT points", zorder=4)
    axes[0].plot(times[:n], (y[:n]-first)/1000, c="tab:orange", lw=2,
                 label="65504: phase/calibration from other curved track")
    axes[0].plot(times[n:], (y[n:]-last)/1000, c="tab:blue", lw=2,
                 label="68214: retained curved suffix")
    axes[0].set(ylabel="Native GLRT CFO (kHz)")
    axes[0].legend(fontsize=9)
    axes[1].plot(times, old_residual, "o-", ms=4, c="crimson")
    axes[1].set(title="Original one-satellite residual: 1,303 Hz RMS; still entered position loss",
                ylabel="Residual (Hz)")
    axes[2].plot(times[:n], first, "o-", ms=4, c="tab:orange",
                 label="12-point prefix: no calibration vote")
    axes[2].plot(times[n:], last, "o-", ms=4, c="tab:blue",
                 label="36-point suffix: calibration eligible")
    axes[2].set(title="Two-family explanation; prefix identity narrowly passes structure gates",
                xlabel="Time from scan anchor (s)", ylabel="Residual (Hz)")
    axes[2].legend(fontsize=9)
    for ax in axes:
        ax.axvspan(times[0]-.5, times[n-1]+.5, color="tab:orange", alpha=.08)
        ax.axvspan(times[n]-.5, times[-1]+.5, color="tab:blue", alpha=.06)
        ax.axvline((times[n-1]+times[n])/2, ls="--", c=".4")
        ax.grid(alpha=.2)
    axes[1].axhline(0, c="black", lw=.7)
    axes[2].axhline(0, c="black", lw=.7)
    fig.suptitle("DS23-0342 RX1 CH2 T002: two candidate emitters across a 6.43 s graph gap")
    save(fig, "S0342_graph_bridge.png")


def phase_pressure():
    arm = read(OUT / "DS23-0039/audit.json")["arms"]["c0"]
    old, gps = arm["replay"], arm["phase_refreshed_at_reference_position"]
    repair = next(r for r in read(GENUINE / "DS23-0039/repairs.json")["results"]
                  if r["variant"] == "causal_phase" and r["arm"] == "c0")
    fig, axes = plt.subplots(2, 1, figsize=(14, 9))
    xx = np.arange(len(arm["families"]))
    axes[0].plot(xx, old["phase_s"], "o-", label="At published position (3.37 km error)")
    axes[0].plot(xx, gps["phase_s"], "o-", label="At supplied reference (diagnostic)")
    axes[0].axhspan(-1, 1, alpha=.12, color=".4", label="Original ±1 s prior scale")
    axes[0].set_xticks(xx, [str(r["norad"]) for r in arm["families"]], rotation=40)
    axes[0].set(ylabel="Fitted satellite phase (s)", xlabel="NORAD satellite")
    axes[0].legend(fontsize=9)
    axes[0].grid(alpha=.2)
    labels = ["Phase prior", "Other priors", "Weighted data", "Covariance volume",
              "Noise scale terms"]
    prior0, prior1 = old["prior_cost"], gps["prior_cost"]
    delta_phase = prior1["phase"]-prior0["phase"]
    delta_other = sum(prior1.values())-sum(prior0.values())-delta_phase
    delta_data = (gps["quadratic"]-sum(prior1.values())
                  -old["quadratic"]+sum(prior0.values()))
    changes = [delta_phase, delta_other, delta_data, gps["logvolume"]-old["logvolume"],
               gps["gamma_cost"]-old["gamma_cost"]]
    bars = axes[1].bar(labels, changes,
                       color=["crimson" if v > 0 else "steelblue" for v in changes])
    axes[1].bar_label(bars, fmt="%+.2f", padding=4)
    axes[1].axhline(0, color="black", lw=.7)
    axes[1].set(ylabel="Score at reference minus score at fitted position",
                title=f"Reference improves raw RMS {old['RMS_hz']:.2f} → {gps['RMS_hz']:.2f} Hz; "
                      f"phase prior adds {delta_phase:.2f} score units")
    axes[1].grid(axis="y", alpha=.2)
    fig.suptitle(f"DS23-0039: overly narrow phase prior pulls position; causal-width fit error "
                 f"{repair['error_km']:.2f} km")
    save(fig, "S0039_phase_prior_pressure.png")


def epoch_gaps():
    old = next(r for r in read(OUT / "DS23-0342/repairs.json")["results"]
               if r["variant"] == "causal_phase" and r["arm"] == "c0")
    new = next(r for r in read(GENUINE / "DS23-0342/repairs.json")["results"]
               if r["variant"] == "causal_phase" and r["arm"] == "c0")
    fig, ax = plt.subplots(figsize=(14, 5))
    x = np.arange(len(old["phase_width_receipt"]))
    for r, dx, label in ((old, -.18, "Original previous-entry selection"),
                          (new, .18, "Genuinely earlier causal entries")):
        ax.bar(x+dx, [q["previous_epoch_gap_s"] for q in r["phase_width_receipt"]],
               width=.34, label=label)
    ax.set_xticks(x, [str(q["norad"]) for q in old["phase_width_receipt"]], rotation=45)
    ax.set_yscale("log")
    ax.set(ylabel="Latest minus previous element epoch (seconds)", xlabel="Nominated satellite")
    ax.axhline(.000864, c="crimson", ls="--", label="0.864 ms round-trip difference")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="y", alpha=.2)
    fig.suptitle("DS23-0342: sub-millisecond duplicate epochs are not independent orbit updates")
    save(fig, "S0342_causal_epoch_duplicates.png")


def polynomial_splits():
    data = read(GENUINE / "DS23-0342/polynomial_split_bic.json")
    rows = sorted(data["splits"], key=lambda r: r["cut"])
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot([(r["before_s"]+r["after_s"])/2 for r in rows],
            [r["bic"] for r in rows], "o-", ms=4, label="Two polynomials plus breakpoint penalty")
    ax.axhline(data["full"]["bic"], ls="--", c="crimson", label="Single quartic")
    physical = next(r for r in rows if r["cut"] == 12)
    ax.scatter((physical["before_s"]+physical["after_s"])/2, physical["bic"],
               marker="*", s=160, c="tab:orange", edgecolors="black",
               label="12 / 36 satellite-based partition")
    ax.set(xlabel="Proposed breakpoint time (s)", ylabel="BIC (lower is better)",
           title="DS23-0342: radio-only model selection also favors a split")
    ax.legend(fontsize=9)
    ax.grid(alpha=.2)
    save(fig, "S0342_polynomial_splits.png")


def loss_maps():
    fig, axes = plt.subplots(2, 2, figsize=(13, 11), sharex=True, sharey=True)
    for row, case in enumerate(CASES):
        data = np.load(GENUINE / case / "surfaces.npz")
        metadata = read(GENUINE / case / "surface_diagnostics.json")["results"]
        for col, mode in enumerate(("baseline", "corrected")):
            ax = axes[row, col]
            x, y = data["east_from_reference_km"], data["north_from_reference_km"]
            values = data[mode+"_c0"]
            endpoint = next(v for v in metadata if v["model"] == mode and v["arm"] == "c0")
            delta = values-endpoint["endpoint_score"]
            ax.contourf(x, y, np.clip(delta, 0, 100),
                        levels=[0, 1, 2, 5, 10, 20, 50, 100], cmap="viridis_r")
            cs = ax.contour(x, y, delta, levels=[1, 2, 5, 10, 20, 50], colors=".3", linewidths=.7)
            ax.clabel(cs, fontsize=8)
            reference_xy = np.array([( -122.48574968092912 + 122.545)
                                     *111.32*np.cos(np.deg2rad(37.906)),
                                     (37.849061591561885-37.906)*111.0])
            point = np.array(endpoint["endpoint"])-reference_xy
            ax.scatter(*point, marker="*", s=210, c="red", edgecolors="black",
                       label="Fitted endpoint", zorder=5)
            ax.scatter(0, 0, marker="+", s=150, c="white", linewidths=3,
                       label="Reference (evaluation only)", zorder=6)
            ax.set(title=f"{case}: {mode}; error {endpoint['error_km']:.2f} km",
                   xlabel="East from reference (km)", ylabel="North from reference (km)")
            ax.set_aspect("equal")
            ax.legend(fontsize=7)
    fig.suptitle("Δ profiled loss, c=0: IDs, aliases and final phase tangent fixed\n"
                 "0.5 km grid; nuisance coefficients and noise precisions refitted at each point")
    save(fig, "loss_surfaces.png")


if __name__ == "__main__":
    comparisons()
    influence()
    bridge()
    phase_pressure()
    epoch_gaps()
    polynomial_splits()
    loss_maps()
