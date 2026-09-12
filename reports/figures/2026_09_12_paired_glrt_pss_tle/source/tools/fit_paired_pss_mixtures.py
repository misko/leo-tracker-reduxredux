"""Fit/replay three PSS peak models on the frozen five-dwell, three-lane cohort."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.research.pss_peak_mixture import (
    evaluate_mixture,
    fit_peak_mixture,
    track_peak_mixture,
)

ROOT = Path("/srv/bulk/leo/experiments")
LANES = ("native25", "derived2p5", "recorded2p5")
LABELS = ("25 MS/s native", "2.5 MS/s downsampled", "2.5 MS/s independent capture")
COLORS = ("#157f91", "#c76524", "#7d58a0")


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def write(path, value):
    path.write_text(json.dumps(value, default=json_default, indent=2, allow_nan=False) + "\n")


def plot_associated_scatter(out, capture, records, glrt):
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.5), constrained_layout=True)
    limits = [80.0, 120.0]
    for col, lane in enumerate(LANES):
        g = next(g for g in glrt if g["capture_id"] == capture and g["lane"] == lane)
        t, residual = np.array(g["time_s"]), np.array(g["periodic_model_residual_ns"])
        late = t >= 1.35
        axes[0, col].scatter(t[late], residual[late], s=12, color=COLORS[col], alpha=0.75)
        axes[0, col].set_title(f"{LABELS[col]}\nGLRT reference · frozen early model")
        axes[0, col].set_ylabel("GLRT late timing residual (ns)")
        limits[0] = max(limits[0], float(np.max(abs(residual[late]))) * 1.08)
        s, r, _ = next(
            row for row in records if row[0]["capture_id"] == capture and row[0]["lane"] == lane
        )
        ds = [d for d in r["decisions"] if d["accepted"]]
        ax = axes[1, col]
        if ds:
            for main, color, marker, label in (
                (True, COLORS[col], ".", "Primary peak"),
                (False, "#2166ac", "s", "Other repetition"),
            ):
                chosen = [d for d in ds if (d["branch"] == 0) == main]
                ax.scatter(
                    [d["time_s"] for d in chosen],
                    [d["branch_innovation_ns"] for d in chosen],
                    s=12 if main else 8,
                    color=color,
                    marker=marker,
                    alpha=0.65,
                    label=label,
                )
            limits[1] = max(limits[1], max(abs(d["branch_innovation_ns"]) for d in ds) * 1.08)
            ax.set_title(
                f"PSS accepted {len(ds)}/{s['late_count']} · "
                f"residual RMS {s['accepted_branch_innovation_rms_ns']:.1f} ns"
            )
            ax.legend(fontsize=8)
        else:
            ax.set_title("PSS · no supported repetition lock")
            ax.text(
                0.5,
                0.5,
                f"All {s['late_count']} late observations withheld\nSee raw-measurement panel",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color="#bd4646",
            )
        ax.set_ylabel("PSS timing residual after peak association (ns)")
    for row in range(2):
        for ax in axes[row]:
            ax.set_xlim(1.35, 2.25)
            ax.set_ylim(-limits[row], limits[row])
            ax.axhline(0, color="#555555", lw=0.5)
            ax.set_xlabel("Seconds into interval · late observations only")
            ax.grid(alpha=0.2)
    fig.suptitle(
        f"Scatter after PSS peak association · dwell {capture[-6:]}\n"
        "PSS: measured timing − prior prediction − associated peak offset; "
        "only posterior ≥95% updates are shown\n"
        "Conditional scatter, not absolute timing accuracy; "
        "all uncertain observations remain visible in the companion raw plots",
        fontsize=12,
    )
    fig.savefig(out / f"associated-residuals-{capture[-6:]}.png", dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    if out.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    out.mkdir(exist_ok=True)
    v2 = ROOT / "paired-five-pss-bandwidth-20260912-v2-fractional"
    v5 = ROOT / "paired-five-pss-outlier-bands-20260912-v5"
    inputs = [v2 / "selection.json", v2 / "summary.json", v5 / "glrt-sample-phase-bias.json"]
    captures = json.loads(inputs[0].read_text())["selected"]
    pss = json.loads(inputs[1].read_text())
    glrt = json.loads(inputs[2].read_text())["records"]
    records = []
    for c in captures:
        for lane in LANES:
            r = next(r for r in pss if r["capture_id"] == c["capture_id"] and r["lane"] == lane)
            t = (
                np.array(r["time_s"])
                - c["recorded_start_s" if lane == "recorded2p5" else "native_start_s"]
            )
            y = np.array(r["phase_s"]) * 1e9
            early, calibration, late = t < 0.9, (t >= 0.9) & (t < 1.35), t >= 1.35
            train = ~late
            models, frozen = {}, {}
            for mode in ("single", "fixed", "empirical"):
                m = fit_peak_mixture(t[train], y[train], mode=mode)
                ll, probability = evaluate_mixture(m, t[late], y[late])
                models[mode] = m
                frozen[mode] = dict(
                    mean_late_log_density=float(ll.mean()),
                    late_log_density=ll,
                    outlier_posterior=probability[:, -1],
                )
            # Choice is declared from earlier v5 evidence, not selected using late results.
            chosen_mode = "fixed" if lane == "native25" else "empirical"
            initial = fit_peak_mixture(t[early], y[early], mode=chosen_mode)
            calibrations = []
            for jerk in (1e3, 1e5, 1e7, 1e9):
                replay = track_peak_mixture(
                    initial, t[calibration], y[calibration], start_s=0.9, jerk_density=jerk
                )
                calibrations.append(
                    dict(
                        jerk_density=jerk,
                        mean_log_density=float(np.mean([d["log_density"] for d in replay])),
                    )
                )
            jerk = max(calibrations, key=lambda d: d["mean_log_density"])["jerk_density"]
            model = models[chosen_mode]
            decisions = track_peak_mixture(model, t[late], y[late], start_s=1.35, jerk_density=jerk)
            accepted = [d for d in decisions if d["accepted"]]
            accepted_mask = np.array([d["accepted"] for d in decisions])
            innovation = np.array([d["branch_innovation_ns"] for d in decisions])
            adjacent = accepted_mask[:-1] & accepted_mask[1:]
            lag_one = (
                float(np.corrcoef(innovation[:-1][adjacent], innovation[1:][adjacent])[0, 1])
                if adjacent.sum() > 4
                else None
            )
            main_count = sum(d["accepted"] and d["branch"] == 0 for d in decisions)
            alias_count = sum(d["accepted"] and d["branch"] != 0 for d in decisions)
            uncertain = sum(d["active"] and not d["accepted"] for d in decisions)
            inactive = sum(not d["active"] for d in decisions)
            summary = dict(
                capture_id=c["capture_id"],
                lane=lane,
                selected_mode=chosen_mode,
                supported=model.supported,
                training_count=int(train.sum()),
                late_count=int(late.sum()),
                fitted_core_sigma_ns=model.sigma_ns,
                fitted_spacing_ns=model.spacing_ns,
                fitted_background_fraction=float(model.weights[-1]),
                early_coherence=model.coherence,
                selected_jerk_density=jerk,
                accepted_main_count=main_count,
                accepted_other_branch_count=alias_count,
                uncertain_count=uncertain,
                inactive_count=inactive,
                accepted_fraction=len(accepted) / len(decisions),
                accepted_branch_innovation_rms_ns=float(
                    np.sqrt(np.mean([d["branch_innovation_ns"] ** 2 for d in accepted]))
                )
                if accepted
                else None,
                late_mean_log_density_gain_vs_single={
                    mode: frozen[mode]["mean_late_log_density"]
                    - frozen["single"]["mean_late_log_density"]
                    for mode in ("fixed", "empirical")
                },
                tracking_mean_log_density=float(np.mean([d["log_density"] for d in decisions])),
                accepted_adjacent_pair_count=int(adjacent.sum()),
                accepted_innovation_lag_one_correlation=lag_one,
            )
            result = dict(
                summary=summary,
                time_s=t,
                measured_phase_ns=y,
                models={mode: asdict(m) for mode, m in models.items()},
                frozen_evaluation=frozen,
                process_calibration=calibrations,
                decisions=decisions,
            )
            write(out / f"{c['capture_id']}-{lane}.json", result)
            records.append((summary, result, model))
            print(summary, flush=True)

    # Complete measurement panels: leave every original peak visible.
    for c in captures:
        fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
        for col, lane in enumerate(LANES):
            g = next(g for g in glrt if g["capture_id"] == c["capture_id"] and g["lane"] == lane)
            axes[0, col].scatter(
                g["time_s"], g["periodic_model_residual_ns"], s=9, color=COLORS[col], alpha=0.7
            )
            axes[0, col].set_title(
                f"{LABELS[col]}\nGLRT reference · existing sample-phase correction"
            )
            axes[0, col].set_ylim(-130, 130)
            axes[0, col].set_ylabel("GLRT timing − early fitted prediction (ns)")
            s, r, model = next(
                row
                for row in records
                if row[0]["capture_id"] == c["capture_id"] and row[0]["lane"] == lane
            )
            t, y = r["time_s"], r["measured_phase_ns"]
            train = t < 1.35
            ax = axes[1, col]
            ax.scatter(
                t[train],
                y[train] - model.predict(t[train]),
                s=5,
                color="#aaaaaa",
                alpha=0.5,
                label="Training measurements",
            )
            ds = r["decisions"]
            for kind, color, marker, label in (
                ("main", COLORS[col], ".", "Accepted primary peak"),
                ("alias", "#2166ac", "s", "Accepted other repetition"),
                ("uncertain", "#bd4646", "x", "Uncertain / inactive"),
            ):
                chosen = [
                    d
                    for d in ds
                    if (
                        (d["accepted"] and d["branch"] == 0)
                        if kind == "main"
                        else (d["accepted"] and d["branch"] != 0)
                        if kind == "alias"
                        else not d["accepted"]
                    )
                ]
                ax.scatter(
                    [d["time_s"] for d in chosen],
                    [d["raw_innovation_ns"] for d in chosen],
                    s=10 if kind != "alias" else 8,
                    color=color,
                    marker=marker,
                    alpha=0.65,
                    label=label,
                )
            if model.supported:
                for k, weight in zip(model.branches, model.weights[:-1], strict=True):
                    if weight > 0.002:
                        center = k * model.spacing_ns
                        ax.axhline(center, color="#555555", lw=0.5, alpha=0.4)
                        ax.axhspan(
                            center - 2 * model.sigma_ns,
                            center + 2 * model.sigma_ns,
                            alpha=0.035,
                            color=COLORS[col],
                        )
            title = (
                f"PSS mixture · core σ {model.sigma_ns:.1f} ns · "
                f"accepted {s['accepted_main_count'] + s['accepted_other_branch_count']}"
                f"/{s['late_count']}"
                if model.supported
                else "PSS · repetition model unsupported; no lock updates"
            )
            ax.set_title(title)
            bound = max(
                3200.0,
                max(abs(d["raw_innovation_ns"]) for d in ds) * 1.05,
                float(np.max(abs(y[train] - model.predict(t[train])))) * 1.05,
            )
            ax.set_ylim(-bound, bound)
            ax.set_ylabel("PSS measured timing − model prediction (ns)")
            ax.legend(fontsize=7, loc="upper left")
            for row in range(2):
                axes[row, col].axvline(1.35, color="#555555", ls=":", lw=1)
                axes[row, col].axvspan(1.35, 2.25, color="#c3dce9", alpha=0.15)
                axes[row, col].set_xlim(0, 2.25)
                axes[row, col].set_xlabel("Seconds into interval · shaded area is late evaluation")
                axes[row, col].grid(alpha=0.15)
        # Equal scales within each row, including weak series with large forecast errors.
        limit = max(ax.get_ylim()[1] for ax in axes[1])
        for ax in axes[1]:
            ax.set_ylim(-limit, limit)
        fig.suptitle(
            f"Updated PSS mixture and causal association · dwell {c['capture_id'][-6:]}\n"
            "Every original peak remains visible; "
            "bands show ±2 fitted core σ, not timing confidence\n"
            "GLRT uses its previous frozen early fit; "
            "PSS late predictions update only from earlier confident associations",
            fontsize=12,
        )
        fig.savefig(out / f"mixture-tracks-{c['capture_id'][-6:]}.png", dpi=150)
        plt.close(fig)
        plot_associated_scatter(out, c["capture_id"], records, glrt)

    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
    x = np.arange(5)
    for col, lane in enumerate(LANES):
        gs = [
            next(g for g in glrt if g["capture_id"] == c["capture_id"] and g["lane"] == lane)
            for c in captures
        ]
        axes[0, col].bar(
            x - 0.17,
            [g["late_baseline_rms_ns"] for g in gs],
            width=0.32,
            color="#aaaaaa",
            label="Quadratic only",
        )
        axes[0, col].bar(
            x + 0.17,
            [g["late_periodic_model_rms_ns"] for g in gs],
            width=0.32,
            color=COLORS[col],
            label="+ sample-phase correction",
        )
        axes[0, col].set_title(f"{LABELS[col]}\nGLRT reference · unchanged late evaluation")
        axes[0, col].set_ylabel("Late timing residual RMS (ns)")
        axes[0, col].set_ylim(0, 65)
        axes[0, col].legend(fontsize=8)
        ss = [
            next(
                s for s, _, _ in records if s["capture_id"] == c["capture_id"] and s["lane"] == lane
            )
            for c in captures
        ]
        bottom = np.zeros(5)
        for key, color, label in (
            ("accepted_main_count", COLORS[col], "Accepted primary peak"),
            ("accepted_other_branch_count", "#2166ac", "Accepted other repetition"),
            ("uncertain_count", "#cccccc", "Uncertain"),
            ("inactive_count", "#bd4646", "Unsupported / lock expired"),
        ):
            heights = 100 * np.array([s[key] / s["late_count"] for s in ss])
            axes[1, col].bar(x, heights, bottom=bottom, color=color, width=0.65, label=label)
            bottom += heights
        axes[1, col].set_title("PSS mixture tracker · every late measurement counted")
        axes[1, col].set_ylabel("Late measurements (%)")
        axes[1, col].set_ylim(0, 136)
        axes[1, col].set_yticks([0, 25, 50, 75, 100])
        axes[1, col].legend(fontsize=7, loc="upper right")
        for row in range(2):
            axes[row, col].set_xticks(x, [c["capture_id"][-6:] for c in captures], rotation=25)
            axes[row, col].grid(axis="y", alpha=0.15)
            axes[row, col].set_axisbelow(True)
    fig.suptitle(
        "Both estimators, all three lanes · updated PSS model support and coverage\n"
        "PSS peak parameters fit first 60%; "
        "process variance selected within early data; late tracking is causal\n"
        "Accepted repetition association is conditional on the model, not absolute arrival truth",
        fontsize=12,
    )
    fig.savefig(out / "mixture-model-status.png", dpi=150)
    plt.close(fig)
    write(out / "summary.json", [s for s, _, _ in records])
    write(
        out / "protocol.json",
        dict(
            inputs={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
            frame_timing_source="frozen corrected fractional PSS v2; no new IQ remeasurement",
            models="single Gaussian+Student-t baseline; "
            "fixed repetition mixture; empirical-spacing mixture",
            mixture_components="13 Gaussian peaks plus df=3 Student-t background, scale 1500 ns",
            empirical_spacing_bounds_ns=[480, 570],
            chosen_mode="fixed at 25 MS/s; empirical at both 2.5 MS/s lanes, "
            "declared before late evaluation",
            training_stop_s=1.35,
            process_training_stop_s=0.9,
            process_calibration_stop_s=1.35,
            process_candidates=[1e3, 1e5, 1e7, 1e9],
            posterior_update_threshold=0.95,
            maximum_coast_s=0.25,
            candidate_acquisition="whole-interval association inherited from v2; "
            "causal replay is conditional",
            uncertainty="curve covariance conditional on spacing and responsibilities; "
            "core sigma includes unmodeled signal effects",
            background_center="ordinary quadratic fitted on the supplied training data, frozen "
            "during mixture optimization and evaluation; same baseline across candidate models",
            fresh_RF=False,
            production_deployment=False,
        ),
    )


if __name__ == "__main__":
    main()
