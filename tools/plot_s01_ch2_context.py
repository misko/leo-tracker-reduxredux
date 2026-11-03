"""Native GLRT context and local RMS diagnostics for the 80-point CH2 track."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from diagnose_s01_ch2_t000 import NORAD, OUTPUT, PROTOTYPES, TARGET
from inventory_clipped_phase_cohort import ROOT, load_study

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run():
    study, *_ = load_study("DSX01-S01", True)
    previous = json.loads((PROTOTYPES / "family_extension/fitted_c/association.json").read_text())
    old = {r["component"]: r for r in previous["rows"]}
    tracks = [t for t in study.tracks if old[t["key"]]["candidate_norad"] == NORAD]
    raw = [
        r
        for line in (
            ROOT / "reports/2026_10_16_dsx01_fast_association_losses" / "context-observations.jsonl"
        )
        .read_text()
        .splitlines()
        if (r := json.loads(line))["source_id"] == "S01"
    ]
    lookup = {r["observation_id"]: r for r in raw}
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, layout="constrained")
    for receiver, ax in enumerate(axes, 1):
        own = [r for r in raw if r["receiver"] == receiver and 215 <= r["time_s"] <= 301]
        ax.scatter(
            [r["time_s"] for r in own],
            [r["measured_cfo_hz"] / 1000 for r in own],
            color="lightgray",
            s=9,
            label="All GLRT, all channels",
        )
        for t in tracks:
            if t["receiver"] != receiver:
                continue
            row = old[t["key"]]
            native = np.array([lookup[oid]["measured_cfo_hz"] for oid in t["observation_ids"]])
            branch = np.rint((t["values"] - native) / (1 / 4.4e-6))
            predicted = t["values"] - np.array(row["residual_hz"]) - branch / 4.4e-6
            target = t["key"] == TARGET
            colors = [
                "royalblue",
                "darkorange",
                "forestgreen",
                "darkviolet",
                "teal",
                "saddlebrown",
                "deeppink",
                "darkcyan",
            ]
            color = "crimson" if target else colors[t["channel"] - 1]
            label = f"CH{t['channel']} {t['key'].split('-')[-1]}: {len(native)} pts, "
            label += "accepted" if row["compatible"] else "unassociated"
            ax.scatter(
                t["times"],
                native / 1000,
                s=36 if target else 17,
                marker="o" if row["compatible"] else "x",
                color=color,
                label=label,
                zorder=5 if target else 3,
            )
            if target:
                dominant = np.median(branch)
                for i in np.flatnonzero(branch != dominant):
                    ax.annotate(
                        "Same track, different CFO alias",
                        (t["times"][i], native[i] / 1000),
                        xytext=(t["times"][i] - 14, native[i] / 1000 + 30),
                        arrowprops=dict(arrowstyle="->", color=color),
                        color=color,
                        fontsize=8,
                    )
            for a, b in zip(range(len(native) - 1), range(1, len(native)), strict=True):
                if branch[a] == branch[b] and t["times"][b] - t["times"][a] < 8:
                    ax.plot(
                        t["times"][[a, b]],
                        predicted[[a, b]] / 1000,
                        color=color,
                        lw=1.7 if target else 0.7,
                        alpha=0.8,
                    )
        ax.set(
            ylabel="Native measured CFO (kHz)",
            title=f"RX{receiver}: 62811 candidate family over all GLRT",
            xlim=(215, 301),
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7, ncol=3, loc="upper right")
    axes[1].set(xlabel="Seconds from S01 start")
    fig.suptitle(
        "DSX01 S01 — the 80-point RX1 CH2 track in context\n"
        "Colored points: candidate-family tracks; "
        "lines: existing orbit + hardware + fragment constant"
    )
    fig.savefig(OUTPUT / "native_glrt_context.png", dpi=170)
    plt.close(fig)

    target = old[TARGET]
    t, r = np.array(target["times_s"]), np.array(target["residual_hz"])
    poly = json.loads((OUTPUT / "polynomial_orders.json").read_text())[0]
    noise = np.array(poly["residual_hz"])
    windows = []
    for lo, hi in ((240, 250), (250, 260), (260, 270), (270, 280), (280, 290), (290, 300)):
        mask = (t >= lo) & (t < hi)
        v = r[mask]
        windows.append(
            dict(
                start_s=lo,
                end_s=hi,
                points=int(mask.sum()),
                mean_hz=float(np.mean(v)),
                rms_about_existing_prediction_hz=float(np.sqrt(np.mean(v**2))),
                scatter_about_local_mean_hz=float(np.std(v)),
                empirical_quartic_noise_rms_hz=float(np.sqrt(np.mean(noise[mask] ** 2))),
            )
        )
    # A fixed, interpretable 275s split, rather than optimizing its location.
    fragments = []
    for name, mask in (("early_before_275s", t < 275), ("late_from_275s", t >= 275)):
        raw_residual = r[mask] + target["bias_hz"]
        bias = raw_residual.sum() / (mask.sum() + 0.0225)
        residual = raw_residual - bias
        diagnostics = batch_noise_screen(residual[None, :], t[mask])
        fragments.append(
            dict(
                name=name,
                points=int(mask.sum()),
                rms_hz=float(np.sqrt(np.mean(residual**2))),
                bias_hz=float(bias),
                passes_residual_gates=bool(diagnostics["noise_screen_pass"][0]),
                diagnostics={
                    k: bool(v[0]) if k == "noise_screen_pass" else float(v[0])
                    for k, v in diagnostics.items()
                },
            )
        )
    write(
        OUTPUT / "time_local_error.json",
        dict(
            windows=windows,
            fixed_split=fragments,
            no_observations_removed=True,
            no_association_changed=True,
            local_centering_diagnostic_only=True,
            no_new_candidate_competition=True,
        ),
    )
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), layout="constrained")
    axes[0].plot(t, r, ".-", color="slategray", label="Residual to current causal orbit")
    axes[0].plot(t, r - noise, color="darkorange", lw=2, label="Smooth polynomial − orbit mismatch")
    for w in windows:
        axes[0].plot([w["start_s"], w["end_s"]], [w["mean_hz"]] * 2, "r-", lw=3)
    axes[0].axhline(0, color="black", lw=0.7)
    axes[0].set(ylabel="Residual (Hz)", title="Late increase contains a shifting mean")
    centers = [(w["start_s"] + w["end_s"]) / 2 for w in windows]
    for key, label, color in (
        ("rms_about_existing_prediction_hz", "RMS to existing prediction", "firebrick"),
        ("scatter_about_local_mean_hz", "Scatter after removing each window mean", "seagreen"),
        ("empirical_quartic_noise_rms_hz", "RMS to empirical quartic", "royalblue"),
    ):
        axes[1].plot(centers, [w[key] for w in windows], "o-", color=color, label=label)
    axes[1].set(
        ylabel="10-second-window RMS / scatter (Hz)",
        title="Prediction RMS rises; local noise scatter does not rise with it",
    )
    for ax in axes:
        ax.set(xlabel="Seconds from S01 start")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(OUTPUT / "local_rms_and_mean.png", dpi=170)
    plt.close(fig)
    print(json.dumps(dict(windows=windows, fixed_split=fragments)))


if __name__ == "__main__":
    run()
