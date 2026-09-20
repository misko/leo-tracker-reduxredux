"""Publish all materially improved track audits and low-dimensional diagnostics."""

import argparse
import csv
import json
import shutil
from pathlib import Path

import numpy as np


def explanation(row):
    if row["identity_changed"]:
        return "Different satellite selected; this is not an orbit update of the same object."
    if row["identical_tle"]:
        return (
            "Identical element set; the pipeline improvement is from the "
            "changed receiver/clock solution."
        )
    g = row["geometry"]
    dominant = ["radial", "along-track", "cross-track"][
        int(np.argmax(g["rtn_position_energy_fraction"]))
    ]
    result = f"Largest position-change component: {dominant}. "
    if g["models"]["phase1"]["orbit_doppler_energy_explained"] >= 0.9:
        result += "A time shift explains at least 90% of held-out orbit-Doppler difference energy. "
    elif g["models"]["rtn3"]["orbit_doppler_energy_explained"] >= 0.9:
        result += (
            "Time shift alone is inadequate; three local offsets explain "
            "at least 90% of Doppler difference energy. "
        )
    else:
        result += (
            "Offset rates matter: even constant three-axis offsets leave "
            "over 10% of Doppler difference energy. "
        )
    if row["controls"][0]["new_rms_hz"] >= row["controls"][0]["old_rms_hz"]:
        result += (
            "The new orbit does not improve measured RMS at the fixed causal position; "
            "do not attribute the pipeline gain to the orbit alone."
        )
    return result.rstrip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(exist_ok=False)
    doc = json.loads(a.input.read_text())
    rows = doc["rows"]
    material = [r for r in rows if r["material_improvement"]]
    geo = [r for r in material if "geometry" in r]
    shutil.copy2(a.input, a.output / "analysis.json")
    names = {
        "phase1": "1: orbital time shift",
        "phase_rate2": "2: shift + time rate",
        "rtn3": "3: constant RTN offsets",
        "rtn6": "6: RTN offsets + rates",
    }
    summary = dict(
        total=len(rows),
        material=len(material),
        identity_changes=sum(r["identity_changed"] for r in material),
        identical_tle=sum(r["identical_tle"] for r in material),
        geometry_count=len(geo),
        models={},
    )
    for name in names:
        summary["models"][name] = {
            k: float(np.median([r["geometry"]["models"][name][k] for r in geo]))
            for k in [
                "position_energy_explained",
                "orbit_doppler_energy_explained",
                "orbit_doppler_mismatch_hz",
                "window_600s_position_rms_m",
            ]
        }
        summary["models"][name]["count_explaining_90pct_doppler_energy"] = sum(
            r["geometry"]["models"][name]["orbit_doppler_energy_explained"] >= 0.9 for r in geo
        )
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fields = [
        "index",
        "session_id",
        "episode_id",
        "causal_norad",
        "retrospective_norad",
        "identity_changed",
        "identical_tle",
        "material_improvement",
        "pipeline_causal_heldout_hz",
        "pipeline_retrospective_heldout_hz",
        "causal_age_h",
        "retrospective_age_h",
    ]
    with (a.output / "all-tracks.csv").open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows({k: r[k] for k in fields} for r in rows)
    lines = [
        "# Every materially improved association",
        "",
        "Material = pipeline held-out RMS lower by at least 20 Hz and 25%. "
        "This is a descriptive threshold, not a statistical significance test.",
        "All RMS values below are Hz. Positive epoch age means before capture; "
        "negative means after. "
        "Common-position controls use fixed UTC and refit only source frequency offsets "
        "on training data.",
        "Geometry coefficients use later orbital states and are diagnostic, "
        "not operational corrections. RTN means radial, along-track and cross-track. "
        "Predicted-orbit Doppler mismatch is not measured-signal RMS.",
        "",
    ]
    for r in sorted(material, key=lambda x: (x["causal_norad"], x["index"])):
        lines.extend(
            [
                f"## Track {r['index']}: NORAD {r['causal_norad']} → {r['retrospective_norad']}",
                f"`{r['session_id']}` · episode `{r['episode_id']}` · "
                f"{r['observations']} observations · {r['span_s']:.1f} s.",
                "",
                f"Epoch age {r['causal_age_h']:.2f} → {r['retrospective_age_h']:.2f} h. "
                f"Pipeline held-out RMS {r['pipeline_causal_heldout_hz']:.2f} → "
                f"{r['pipeline_retrospective_heldout_hz']:.2f}.",
                f"At fixed causal position: {r['controls'][0]['old_rms_hz']:.2f} → "
                f"{r['controls'][0]['new_rms_hz']:.2f}; at fixed retrospective position: "
                f"{r['controls'][1]['old_rms_hz']:.2f} → {r['controls'][1]['new_rms_hz']:.2f}.",
                "",
                explanation(r),
                "",
            ]
        )
        if "geometry" in r:
            g = r["geometry"]
            R, T, N = g["rtn_mean_km"]
            lines.extend(
                [
                    f"Mean update ΔR/ΔT/ΔN = {R:+.3f}/{T:+.3f}/{N:+.3f} km. "
                    f"Best orbital shift {g['phase_s']:+.4f} s; "
                    f"affine rate {g['affine_rate_ppm']:+.2f} ppm.",
                    f"Common-epoch plane change {g['plane_change_deg']:.6f}°; "
                    f"osculating semimajor-axis change {g['common_epoch_delta_a_m']:+.1f} m; "
                    "eccentricity-vector change magnitude "
                    f"{g['common_epoch_delta_e_vector_norm']:.6g}.",
                    f"TLE mean eccentricity {g['mean_eccentricity_before']:.7f} → "
                    f"{g['mean_eccentricity_after']:.7f}; "
                    f"mean-motion change {g['raw_mean_motion_change_rev_day']:+.7f} rev/day; "
                    f"BSTAR {g['bstar_before']:.6g} → {g['bstar_after']:.6g}. "
                    "Raw TLE fields refer to different epochs and are not direct physical "
                    "state changes.",
                    f"Local RTN change rates: {', '.join(f'{v:+.3f}' for v in g['rtn_rate_m_s'])} "
                    "m/s. Doppler mismatch before correction: "
                    f"{g['baseline_orbit_doppler_mismatch_hz']:.2f} Hz.",
                    "",
                    "| Diagnostic model | Held-out orbit Doppler mismatch (Hz) | "
                    "Position mismatch (m) | ±300 s position mismatch (m) |",
                    "|---|---:|---:|---:|",
                ]
            )
            for name, label in names.items():
                m = g["models"][name]
                lines.append(
                    f"| {label} | {m['orbit_doppler_mismatch_hz']:.3f} | "
                    f"{m['position_rms_m']:.3f} | {m['window_600s_position_rms_m']:.2f} |"
                )
            lines.append("")
    (a.output / "all-improved-tracks.md").write_text("\n".join(lines).rstrip() + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    shifts = np.array([r["geometry"]["phase_s"] for r in geo])
    p05, median, p95 = np.percentile(shifts, [5, 50, 95])
    fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
    edges = np.arange(np.floor(shifts.min() * 4) / 4, shifts.max() + 0.25, 0.25)
    ax.axvspan(p05, p95, color="#e7eef5", label="Central 90% of tracks")
    ax.hist(shifts, bins=edges, color="#3274a1", edgecolor="white", zorder=2)
    ax.axvline(0, color="#444444", linestyle="--", label="No correction")
    ax.axvline(median, color="#c45b20", linewidth=2, label=f"Median {median:+.2f} s")
    ax.set(
        xlabel="Orbital time correction τ (seconds): old orbit evaluated at t + τ",
        ylabel="Number of tracks (0.25 s bins)",
        title="Distribution of orbital time corrections\n"
        f"{len(geo)} materially improved same-satellite tracks · "
        f"{len(set(r['causal_norad'] for r in geo))} satellites",
    )
    ax.text(
        0.98,
        0.62,
        f"5th–95th percentiles: {p05:+.2f} to {p95:+.2f} s\n"
        f"Full range: {shifts.min():+.2f} to {shifts.max():+.2f} s",
        transform=ax.transAxes,
        ha="right",
        va="top",
    )
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    fig.supxlabel(
        "Negative τ moves the old prediction backward along its orbit. "
        "Receiver UTC is unchanged.\n"
        "Retrospective diagnostic; one value per track, not an unbiased satellite population.",
        fontsize=10,
    )
    fig.savefig(a.output / "time-corrections-histogram.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    gs = [r["geometry"] for r in geo]
    for name, label in names.items():
        vals = np.sort([g["models"][name]["orbit_doppler_mismatch_hz"] for g in gs])
        axes[0, 0].plot(vals, np.arange(1, len(vals) + 1) / len(vals), label=label)
    axes[0, 0].set(
        xscale="log",
        xlabel="Held-out predicted-orbit Doppler mismatch (Hz)",
        ylabel="Fraction of tracks",
        title="Low-dimensional approximation of the orbit update",
    )
    axes[0, 0].legend(fontsize=8)
    frac = np.array([g["rtn_position_energy_fraction"] for g in gs])
    axes[0, 1].boxplot(
        [frac[:, i] * 100 for i in range(3)],
        tick_labels=["Radial", "Along-track", "Cross-track"],
        showfliers=False,
    )
    axes[0, 1].set(
        ylabel="Share of squared position difference (%)",
        title="Most orbit-update displacement is along-track",
    )
    scatter = axes[1, 0].scatter(
        [r["causal_age_h"] for r in geo],
        [g["phase_s"] for g in gs],
        c=np.abs([g["rtn_mean_km"][0] for g in gs]),
        s=16,
        cmap="viridis",
    )
    axes[1, 0].set(
        xlabel="Causal TLE epoch age (h)",
        ylabel="Best orbital time shift (s)",
        title="A per-satellite orbital shift, not a receiver clock shift",
    )
    fig.colorbar(scatter, ax=axes[1, 0], label="Absolute radial change (km)")
    axes[1, 1].scatter(
        [r["controls"][0]["old_rms_hz"] for r in material],
        [r["controls"][0]["new_rms_hz"] for r in material],
        s=16,
    )
    lim = max(max(r["controls"][0][k] for r in material) for k in ["old_rms_hz", "new_rms_hz"])
    axes[1, 1].plot([0, lim], [0, lim], "k--")
    axes[1, 1].set(
        xlabel="Strict TLE measured held-out RMS (Hz)",
        ylabel="Retrospective TLE measured held-out RMS (Hz)",
        title="Common causal receiver position and fixed UTC",
    )
    for ax in axes.ravel():
        ax.grid(alpha=0.2)
    fig.suptitle(
        f"{len(material)} materially improved pipeline tracks; "
        f"{len(geo)} same-satellite orbit changes\n"
        "Later states diagnose update structure; they are not admissible operational inputs"
    )
    fig.savefig(a.output / "overview.png", dpi=160)
    plt.close(fig)
    examples = [next(r for r in geo if r["index"] == i) for i in [153, 198, 115, 336]]
    fig, axes = plt.subplots(4, 2, figsize=(14, 13), layout="constrained")
    for axrow, r in zip(axes, examples, strict=True):
        g = r["geometry"]
        p = g["plot_data"]
        t = p["time_s"]
        axrow[0].scatter(t, p["old_residual_hz"], s=13, label="Strict TLE")
        axrow[0].scatter(t, p["new_residual_hz"], s=13, label="Retrospective TLE")
        axrow[0].set(
            title=f"NORAD {r['causal_norad']} · track {r['index']} · same receiver position",
            ylabel="Measured − model, offset removed (Hz)",
        )
        for name in ["phase1", "rtn3", "rtn6"]:
            axrow[1].plot(t, p["model_mismatch_hz"][name], ".", label=names[name], ms=4)
        axrow[1].set(
            title=f"Update: ΔR/T/N = {' / '.join(f'{v:+.2f}' for v in g['rtn_mean_km'])} km",
            ylabel="New orbit − corrected old orbit (Hz)",
        )
        for ax in axrow:
            ax.axhline(0, color="gray", lw=0.6)
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
            ax.set_xlabel("Seconds since capture start")
    fig.suptitle(
        "Examples: phase-dominated changes and radial/shape exceptions\n"
        "Source frequency offsets are fitted on random training observations; "
        "all retained points shown"
    )
    fig.savefig(a.output / "examples.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
