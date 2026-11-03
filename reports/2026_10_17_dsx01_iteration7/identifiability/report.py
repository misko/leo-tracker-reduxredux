"""Presentation of the sealed original-endpoint surrogate; no model calls."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCES = ("S01", "S02", "S03", "S04", "S05")
ARMS = ("fitted-c", "deterministic-c0-zero-only")
STAGES = (
    "raw",
    "after_calibration",
    "after_calibration_and_timing",
    "after_calibration_and_timing_with_actual_priors",
)


def save(fig, name):
    for suffix in ("png", "pdf"):
        fig.savefig(HERE / f"{name}.{suffix}", dpi=170, bbox_inches="tight")
    plt.close(fig)


def main():
    summary = json.loads((HERE / "summary.json").read_text())
    rows = summary["rows"]
    lookup = {(r["source_id"], r["arm"]): r for r in rows}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for arm, color in zip(ARMS, ("#2676ad", "#d17e2e"), strict=True):
        current = [lookup[s, arm] for s in SOURCES]
        axes[0].plot(
            SOURCES,
            [100 * r["information"]["after_calibration"]["trace_fraction_of_raw"] for r in current],
            "o-",
            color=color,
            label=arm,
        )
        for stage, style in (
            ("after_calibration_and_timing", "o-"),
            ("after_calibration_and_timing_with_actual_priors", "s--"),
        ):
            label = f"{arm}: {'actual priors' if 'priors' in stage else 'data only'}"
            axes[1].plot(
                SOURCES,
                [100 * r["information"][stage]["trace_fraction_of_raw"] for r in current],
                style,
                color=color,
                label=label,
            )
    axes[0].set(
        title="After calibration5 + clocks", ylabel="Retained spatial-information trace (%)"
    )
    axes[1].set(
        title="After calibration + independent satellite timing",
        ylabel="Retained spatial-information trace (%)",
    )
    for ax in axes:
        ax.legend(fontsize=7, frameon=False)
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Original full endpoints: positive fixed-posterior frequency surrogate, not covariance"
    )
    fig.tight_layout()
    save(fig, "information_fractions")
    fig, axes = plt.subplots(4, 2, figsize=(11, 12), sharex=True)
    stage_names = ("Raw", "After calibration", "After calibration + timing", "With actual priors")
    for col, arm in enumerate(ARMS):
        for row, stage in enumerate(STAGES):
            values = np.array(
                [lookup[s, arm]["information"][stage]["eigenvalues_per_km2"] for s in SOURCES]
            )
            axes[row, col].plot(SOURCES, values[:, 0], "o-", label="Weak eigenvalue")
            axes[row, col].plot(SOURCES, values[:, 1], "s--", label="Strong eigenvalue")
            axes[row, col].set(
                yscale="log",
                ylabel="NLL-equivalent / km²",
                title=f"{'Fitted c' if col == 0 else 'c=0 zero-only'}: {stage_names[row]}",
            )
            axes[row, col].grid(alpha=0.2)
            if row == 0:
                axes[row, col].legend(fontsize=8, frameon=False)
    fig.suptitle("Local positive eigenvalues: no observed-Hessian, covariance or accuracy claim")
    fig.tight_layout()
    save(fig, "spatial_eigenvalues")
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    colors = plt.get_cmap("tab10").colors
    for ax, arm in zip(axes, ARMS, strict=True):
        for i, s in enumerate(SOURCES):
            for stage, style in (("raw", "--"), ("after_calibration_and_timing", "-")):
                vectors = np.asarray(
                    lookup[s, arm]["information"][stage]["eigenvectors_regional_east_north_columns"]
                )
                v = vectors[:, 0]
                ax.plot(
                    [-v[0], v[0]],
                    [-v[1], v[1]],
                    style,
                    color=colors[i],
                    label=f"{s} " + ("raw" if stage == "raw" else "projected"),
                )
        ax.set(
            aspect="equal",
            xlim=(-1.1, 1.1),
            ylim=(-1.1, 1.1),
            xlabel="Regional east component",
            ylabel="Regional north component",
            title=arm,
        )
        ax.axhline(0, color=".8")
        ax.axvline(0, color=".8")
        ax.legend(fontsize=6, ncol=2, frameon=False)
    fig.suptitle("Weak eigenvector axes (sign arbitrary): raw versus calibration+timing projection")
    fig.tight_layout()
    save(fig, "weak_axes")

    lines = [
        "# Original full-endpoint identifiability audit",
        "",
        "Calibration plus satellite timing can locally imitate99.48–99.78% of the positive "
        "spatial-frequency information trace at all five original fitted-c endpoints. This "
        "generalizes the local confounding observation beyond one recording. It does not "
        "show that their locations are correct, explain global mode ranking or provide a "
        "position covariance. No station/reference coordinates or requested-window labels "
        "were read in this audit.",
        "",
        f"The one-worker run completed in{summary['elapsed_seconds']:.3f}s under the180s "
        "whole preparation/analysis cap (TERM180/KILL185). It made10 explicit objective "
        "evaluations and10 explicit derivative-predictor calls, plus public original-source "
        "preparation/audits, with zero fits. All20084 original full rows and the original "
        "ordered candidate banks are retained. Original endpoints came from public production "
        "replay, not later profile winners or position-selected states.",
        "",
        "## Fitted-c retained information",
        "",
        "| Source | N / candidates | Signal responsibility mass | After cal+clock % | "
        "After cal+clock+timing % | With actual clock/timing priors % | Nuisance rank |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for source in SOURCES:
        r = lookup[source, ARMS[0]]
        i = r["information"]
        stage = i["after_calibration_and_timing"]
        lines.append(
            f"| {source} | {r['observations']} / {r['candidates']} | "
            f"{r['responsibility_signal_mass']:.3f} | "
            f"{100 * i['after_calibration']['trace_fraction_of_raw']:.4f} | "
            f"{100 * stage['trace_fraction_of_raw']:.4f} | "
            f"{100 * i[STAGES[-1]]['trace_fraction_of_raw']:.4f} | "
            f"{stage['nuisance_rank']}/{stage['nuisance_columns']} |"
        )
    lines += [
        "",
        "Calibration5 plus the18 clock coordinates alone leaves25.89–43.29% of the "
        "raw trace. Most further loss occurs when the independent total-satellite timing "
        "columns are added. Exact existing priors restore only a small fraction of that "
        "loss. This is unconstrained local linear projection, not a demonstrated feasible "
        "finite movement through bounds, assignment changes or global orbital modes.",
        "",
        "## Deterministic c0 sensitivity, no refit",
        "",
        "The c0 arm changes only c to zero at exactly the same original geography and "
        "complete nuisance/timing state. Its current posterior weights change, so this is "
        "not a matched-weight information comparison or an optimized c0 ablation. Both "
        "primary projections use the same five-calibration-column span. The additional "
        "four-coefficient result removes the c direction explicitly.",
        "",
        "| Source | Signal mass | cal+timing retained % (5coef) | With priors % | "
        "cal+timing retained % (c fixed, 4coef) |",
        "|---|---:|---:|---:|---:|",
    ]
    for source in SOURCES:
        r = lookup[source, ARMS[1]]
        i = r["information"]
        restricted = r["c0_fixed_coefficient_projection"]["after_calibration_and_timing"]
        lines.append(
            f"| {source} | {r['responsibility_signal_mass']:.3f} | "
            f"{100 * i[STAGES[2]]['trace_fraction_of_raw']:.4f} | "
            f"{100 * i[STAGES[-1]]['trace_fraction_of_raw']:.4f} | "
            f"{100 * restricted['trace_fraction_of_raw']:.4f} |"
        )
    lines += [
        "",
        "## Eigenvalues, axes and units",
        "",
        "| Source / arm | Raw weak / strong eigenvalues | After cal+timing weak / strong | "
        "Projected weak axis degrees from east (mod180) |",
        "|---|---:|---:|---:|",
    ]
    for r in rows:
        raw = r["information"]["raw"]
        projected = r["information"][STAGES[2]]
        a, b = raw["eigenvalues_per_km2"]
        c, d = projected["eigenvalues_per_km2"]
        angle = projected["eigenvector_angles_deg_from_east"][0] % 180
        lines.append(
            f"| {r['source_id']} / {r['arm']} | {a:.3f} / {b:.3f} | "
            f"{c:.3f} / {d:.3f} | {angle:.3f} |"
        )
    lines += [
        "",
        "All matrices have units NLL-equivalent/km². The saved field name "
        "`information_hz_gaussian_per_km2` denotes its frequency-Gaussian origin; it does "
        "not add an extra Hz factor. Eigenvectors are regional east/north unit axes with "
        "arbitrary sign. Full matrices, generalized raw-relative eigenfractions, raw signed "
        "eigenvalues, nuisance spectra, column norms and cutoff sensitivity are retained "
        "in summary.json. No inverse-information distance, error ellipse or standard error "
        "is claimed.",
        "",
        "Nuisance columns have different physical units and are first normalized to unit "
        "data or data+prior norm. The column span is preserved; eigenspace rank uses1e-12 "
        "of the normalized Gram maximum (with a unit floor), with predeclared1e-10/1e-14 "
        "sensitivity. All primary fitted projected nuisance blocks are full rank, and their "
        "reported trace fractions are unchanged at those two sensitivity cutoffs. This "
        "is not a rank threshold fitted to obtain a desired answer.",
        "",
        "## Exact existing priors and clock scale",
        "",
        "Actual archived clock precision is verified against the entire node/null-basis "
        "matrix for every source and arm. It implies prior_scale4:200Hz amplitude and100Hz "
        "node-second-difference penalty widths, not the class defaults50/25. These are "
        "penalty widths in that clock basis, not pointwise marginal oscillator uncertainty. "
        "Each RX has its own clock common across bands; node constant/linear modes are "
        "removed by its null basis. The3s recording-time prior is separate from these "
        "Hz-valued receiver-frequency clocks.",
        "",
        "The five affine/RF coefficients have no Gaussian prior. The ridge adds exactly "
        "the existing clock precision and total-time precision "
        "`(I−11ᵀ/K)/4 + 11ᵀ/(9K²)`. This preserves the3s common mean and2s relative priors "
        "once. Each actual endpoint prior ledger closes after adding unchanged q and "
        "fixed-band penalties. There is no added geography ridge, q curvature in the "
        "frequency-mean projection or invented timing-age uncertainty.",
        "",
        "## Interpretation and qualification",
        "",
        "Weights are each arm’s current satellite responsibilities divided by actual "
        "per-row sigma². q, candidate signal masses, signal/clutter totals and support "
        "counts are saved. In this sample, signal responsibility on hard-invisible or "
        "below1% soft-visibility alternatives is zero. This does not remove visibility’s "
        "normalizer derivatives from the actual objective; those effects are deliberately "
        "absent from the positive frequency-only surrogate.",
        "",
        "The actual observed mixture Hessian also includes changing assignments/q/visibility, "
        "residual curvature, interpolation structure and bounds. The positive surrogate "
        "does not measure those terms or global ambiguity. Large local confounding is "
        "therefore not an accuracy ranking, proof of wrong timestamps, or justification "
        "for arbitrary prior tightening or more geographic starts.",
        "",
        "Five component tests pass: explicit small-design versus block projection, span "
        "invariance under unit changes/redundant gauges, ridge PSD and common-time prior, "
        "zero-support/dimension guards, and actual4x clock-scale reconciliation. No giant "
        "n*k*parameter tensor is allocated. Each actual source checks original fitted "
        "classification, all-row dimensions, posterior mass closure, exact prior ledger "
        "and immutable source bindings. One cosmetic102-character metadata string in the "
        "frozen runner triggers Ruff E501; it has no numerical effect and is left unchanged "
        "to preserve the run’s source authority. All numerical failures would have remained "
        "durable; this run completed without one.",
        "",
        "Artifacts: summary.json plus ten source/arm JSONs contain the complete matrices "
        "and support/prior metadata. information_fractions.png/.pdf, spatial_eigenvalues.png/.pdf "
        "and weak_axes.png/.pdf are presentation only. No fits, RF, provider changes, "
        "production changes or prior/threshold tuning followed these results.",
    ]
    (HERE / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
