"""Summarize causal covariance and prior-mean tests without GPS selection."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_causal_correlation import CASES, OUTPUT, SPECS
from report_dsx01_joint_marginal import dump_csv

matplotlib.use("Agg")
import matplotlib.pyplot as plt

INPUT = OUTPUT


def run():
    rows, details, ablations, bindings = [], {}, [], {}
    for case in CASES:
        directory = INPUT / "evaluation" / case
        rows += json.loads((directory / "summary.json").read_text())
        ablations += json.loads((directory / "c_ablation.json").read_text())
        details.update(
            {
                f"{case}/{k}": v
                for k, v in json.loads((directory / "details.json").read_text()).items()
            }
        )
        bindings.update(json.loads((directory / "bindings.json").read_text()))
    if len(rows) != 300 or len(ablations) != 50:
        raise ValueError("all300 fit records and50 final matched pairs are required")
    final = [r for r in rows if r["final"]]
    selection = []
    for case in CASES:
        chosen = min(
            [r for r in final if r["case"] == case and r["arm"] == "c0"],
            key=lambda r: r["full_score"],
        )
        partner = next(
            r
            for r in final
            if (r["case"], r["variant"], r["arm"]) == (case, chosen["variant"], "fitted_c")
        )
        selection.append(
            dict(
                case=case,
                variant=chosen["variant"],
                error_c0_km=chosen["position_error_km"],
                error_fitted_c_km=partner["position_error_km"],
            )
        )
    for name, value in [
        ("evaluation_summary", rows),
        ("frequency_details", details),
        ("c_ablation", ablations),
        ("evaluation_bindings", bindings),
        ("c0_model_selection", selection),
    ]:
        write(OUTPUT / (name + ".json"), value)
    dump_csv(OUTPUT / "evaluation_summary.csv", rows)
    dump_csv(OUTPUT / "c_ablation.csv", ablations)
    variants = list(SPECS)
    fig, axes = plt.subplots(1, 2, figsize=(15, 8), sharey=True)
    for ax, arm in zip(axes, ["c0", "fitted_c"], strict=True):
        values = np.array(
            [
                [
                    next(
                        r["position_error_km"]
                        for r in final
                        if (r["case"], r["variant"], r["arm"]) == (case, v, arm)
                    )
                    for case in CASES
                ]
                for v in variants
            ]
        )
        im = ax.imshow(values, vmin=0, vmax=3, cmap="YlOrRd", aspect="auto")
        ax.set_title(arm)
        ax.set_yticks(range(len(variants)), variants)
        ax.set_xticks(range(len(CASES)), [c[-3:] for c in CASES])
        for (i, j), value in np.ndenumerate(values):
            ax.text(j, i, f"{value:.3f}", ha="center", va="center")
    fig.colorbar(im, ax=axes, label="Independent position error (km)", fraction=0.025, pad=0.04)
    fig.savefig(OUTPUT / "position_errors.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    compare = ["diag_4", "corr_6_0p9", "phase_trend", "full_trend", "phase_history", "full_history"]
    components = [
        "weighted_data",
        "shared_prior",
        "curve_constant_prior",
        "noise_gamma",
        "nuisance_logvolume",
    ]
    for ax, case in zip(axes, ["DSX01-S03", "DSX01-S05"], strict=True):
        positive = np.zeros(len(compare))
        negative = positive.copy()
        for component in components:
            values = np.array(
                [details[f"{case}/{v}/c0"]["GPS_minus_endpoint_cost"][component] for v in compare]
            )
            ax.bar(
                range(len(compare)),
                values,
                bottom=np.where(values >= 0, positive, negative),
                label=component,
            )
            positive += np.maximum(values, 0)
            negative += np.minimum(values, 0)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(case)
        ax.set_xticks(range(len(compare)), compare, rotation=35, ha="right")
        ax.set_ylabel("Evaluation GPS minus blind endpoint cost")
    axes[-1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "prior_cost_drivers.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    histories = {}
    for case in CASES:
        history = details[f"{case}/phase_history/c0"]["history_selection"]
        histories[case] = history
        candidate = np.array(history["candidates"])
        loss = np.array(history["robust_phase_proxy_loss"])
        ax.plot(
            candidate,
            loss - loss[0],
            ".-",
            label=case + f" ({len(history['transitions'])} past transitions)",
        )
        chosen = int(np.argmin(loss))
        ax.plot(candidate[chosen], loss[chosen] - loss[0], "o", color="black", markersize=4)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Causal history shrinkage")
    ax.set_ylabel("Past TLE proxy loss relative to no correction")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "history_shrinkage.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    write(OUTPUT / "past_only_history_selection.json", histories)
    exact = [
        r["exact_orbit_mean_rms_hz"] for r in final if r["exact_orbit_mean_rms_hz"] is not None
    ]
    missing = [r for r in final if r["exact_orbit_check_error"] is not None]
    lines = [
        "# DSX01: causal orbital covariance and prior-mean corrections",
        "",
        "**The independent all-five sub-1 km goal remains open.** Ten declared variants "
        "were evaluated with unchanged curved observations and matched zero/fitted RF "
        "calibration arms. No per-scan GPS winner is assembled into a method.",
        "",
        "The previous [strict linear-transfer controls](../2026_10_18_dsx01_cut_linear/README.md) "
        "showed that apparent S05 sub-1 km gains did not survive residual screening. "
        "Here all 12,724 original curved observations remain across the five independent "
        "scans. Linear fragments do not calibrate the hardware and are not added to these "
        "new localization objectives. No observations are held out and no RF was collected.",
        "",
        "Each variant searches the 25 × 25 km Mill Valley box centered at 37.906°, "
        "−122.545° with 25 grid nodes plus a blind incumbent, three c0-selected starts, "
        "24 bounded iterations per start/arm and three phase-reference rounds. Labels, "
        "aliases, measured point-noise scales and remaining priors match within each c "
        "pair. Evaluation GPS enters only the reporter and explicitly labeled postfit "
        "diagnostics. These are exploratory tests on the same corpus.",
        "",
        "Three remedies are tested:",
        "",
        "1. **Correlated orbital priors.** Project the previous/latest causal state "
        "difference at 0/150/300 seconds onto standardized phase, mean-motion, "
        "inclination and RAAN directions. Velocity differences receive a declared "
        "150-second weight. A rank-one correlation uses fractions 0.5 or 0.9 while "
        "preserving every marginal variance. The correlation is a sensitivity hypothesis, "
        "not an empirically calibrated covariance.",
        "2. **A fuller physical span.** Add "
        "both eccentricity-vector directions, using the existing causal scales. Compare "
        "independent and correlated six-coordinate priors to the four-coordinate control.",
        "3. **Causal prior means.** Extrapolate the previous/latest state innovation "
        "opposite its observed direction by `clip(age/epoch_gap,0,2)`. Compare phase-only "
        "and full four-coordinate means, capped at three standardized units. Fixed "
        "unshrunk controls are compared with shrinkage selected using earlier, strictly "
        "causal TLE transitions and no radio measurements or GPS.",
        "",
        "Past-transition selection considers 0/0.25/0.5/0.75/1, using robust normalized "
        "along-track phase-proxy loss. It selects 0.25 for S01/S02/S03/S05 and 0 for "
        "S04. Future records are removed into a separate past-only input before fitting. "
        "A later causal TLE is a consistency proxy, not independent orbit truth.",
        "",
        "![Past-only shrinkage selection](history_shrinkage.png)",
        "",
        "| Variant | S01 | S02 | S03 | S04 | S05 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for v in variants:
        values = []
        for case in CASES:
            pair = [
                next(r for r in final if (r["case"], r["variant"], r["arm"]) == (case, v, a))
                for a in ["c0", "fitted_c"]
            ]
            values.append(" / ".join(f"{r['position_error_km']:.3f}" for r in pair))
        lines.append("| " + v + " | " + " | ".join(values) + " |")
    lines += [
        "",
        "Position errors are km, **c0 / fitted c**. `diag_4` reproduces the previous "
        "normal control.",
        "",
        "![Independent position comparisons](position_errors.png)",
        "",
        "A common c0 normalized-bound selection rule gives "
        + "; ".join(
            f"{r['case']} {r['variant']} ({r['error_fitted_c_km']:.3f} km fitted c)"
            for r in selection
        )
        + ". It also fails the all-scan target. Variational-bound tightness and uncertain "
        "identities limit its interpretation as model evidence.",
        "",
        "Correlations improve some scans and worsen S05. Full unshrunk trend means "
        "bring S03 closer but worsen other scans. The past-only shrinkage rule generally "
        "prefers a modest correction; this does not yield uniform sub-1 km localization.",
        "",
        "![Cost drivers at true versus blind position](prior_cost_drivers.png)",
        "",
        "| Fitted-c variant | Accepted curved points | % curved | Curves | Points/curve "
        "| Common-point RMS c0 / fitted c (Hz) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for v in variants:
        rr = [r for r in final if r["variant"] == v and r["arm"] == "fitted_c"]
        n = sum(r["white_gate_points"] for r in rr)
        tracks = sum(r["white_gate_curves"] for r in rr)
        aa = [a for a in ablations if a["variant"] == v]
        common = sum(a["common_points"] for a in aa)
        rms = [
            np.sqrt(
                sum(a[f"native_rms_{arm}_hz"] ** 2 * a["common_points"] for a in aa)
                / max(1, common)
            )
            for arm in ["c0", "fitted_c"]
        ]
        lines.append(
            f"| {v} | {n:,} | {100 * n / 12724:.2f}% | {tracks} | {n / max(1, tracks):.2f} "
            f"| {rms[0]:.3f} / {rms[1]:.3f} |"
        )
    lines += [
        "",
        "Coverage refers to nominated curved fragments, not all raw GLRT points. "
        "Original RMS, offset, residual-structure, elevation and curved-owner gates "
        "remain in place. Frequency-fit improvements do not establish better position "
        "accuracy. Common-point RMS compares the same accepted population in each c pair.",
        "",
        "The late S05 63387 diagnosis holds receiver calibration fixed and fits one "
        "phase using only its 98 curved points, with identical phase priors and "
        "150 Hz noise in causal/following comparisons. The first following TLE changes "
        "phase by roughly 2.65 seconds, but the late RX2 slope errors persist. They are "
        "also not a uniform receiver effect: unrelated late curved candidates have "
        "different residual slopes. This does not establish a receiver fault, a TLE "
        "maneuver or a correct satellite identity.",
        "",
        "![Following TLE as a postfit diagnostic only](late_family/63387_phase_transfer.png)",
        "",
        "[Detailed late-family diagnosis](late_family/diagnostic.json). No following "
        "TLE enters the new fits.",
        "",
        f"Exact combined SGP4 conditional-mean checks reach **{max(exact):.3f} Hz RMS** "
        f"across {len(exact)} available final endpoints; **{len(missing)}** are unavailable. "
        "These check means, not exact nonlinear marginalization or identity.",
        "",
        "Tests independently verify unchanged covariance marginals, positive variance "
        "floors, latent-coordinate densities against dense Gaussian calculations, state "
        "projections, strict history causality and nonzero-mean variational bounds "
        "against numerical quadrature. A [historical-TLE orbit study]("
        "https://arxiv.org/abs/1002.2277) motivates looking for information in successive "
        "element sets; its batch high-precision orbit method does not validate our simple "
        "few-TLE trend extrapolator.",
        "",
        "[Evaluation CSV](evaluation_summary.csv), [common-point c controls](c_ablation.csv), "
        "[gate/cost details](frequency_details.json), [bindings](evaluation_bindings.json).",
        "",
        "The next investigation should test identity/fragment integrity and "
        "cross-channel coherent residual structure, rather than assume that another "
        "independent prior widening will fix all scans.",
        "",
    ]
    (OUTPUT / "README.md").write_text("\n".join(lines))
    print(
        json.dumps(
            dict(
                records=len(rows),
                pairs=len(rows) // 2,
                max_objective_replay_error=max(r["objective_replay_error"] for r in rows),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    run()
