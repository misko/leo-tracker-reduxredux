"""Aggregate completed prior-bias iterations without GPS-based model selection."""

import json
import re

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_prior_bias_iterations import CASES, OUTPUT, ROOT, SPECS
from report_dsx01_joint_marginal import dump_csv

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def figures(rows, details):
    variants = list(SPECS)
    final = [r for r in rows if r["final"]]
    fig, axes = plt.subplots(1, 2, figsize=(15, max(7, len(variants) * 0.5)))
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        values = np.array(
            [
                [
                    next(
                        r["position_error_km"]
                        for r in final
                        if r["case"] == c and r["variant"] == v and r["arm"] == arm
                    )
                    for c in CASES
                ]
                for v in variants
            ]
        )
        im = ax.imshow(values, vmin=0, vmax=3, cmap="YlOrRd", aspect="auto")
        ax.set(
            xticks=range(5),
            xticklabels=[c[-3:] for c in CASES],
            yticks=range(len(variants)),
            yticklabels=variants,
            title=arm,
        )
        for (i, j), value in np.ndenumerate(values):
            ax.text(
                j,
                i,
                f"{value:.3f}",
                ha="center",
                va="center",
                color="white" if value > 2 else "black",
            )
    fig.subplots_adjust(left=0.16, right=0.86, wspace=0.6)
    fig.colorbar(im, cax=fig.add_axes([0.91, 0.15, 0.015, 0.7]), label="Position error (km)")
    fig.savefig(OUTPUT / "position_errors.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    selected = ["normal", "tail_4", "phase_bias", "weak_3", "rf_time_2"]
    for ax, case in zip(axes, ("DSX01-S03", "DSX01-S05"), strict=True):
        positive, negative = np.zeros(len(selected)), np.zeros(len(selected))
        for key in [
            "weighted_data",
            "shared_prior",
            "curve_constant_prior",
            "noise_gamma",
            "prior_gamma",
            "nuisance_logvolume",
        ]:
            values = np.array(
                [details[f"{case}/{v}/c0"]["GPS_minus_endpoint_cost"][key] for v in selected]
            )
            ax.bar(
                range(len(selected)),
                values,
                bottom=np.where(values >= 0, positive, negative),
                label=key,
            )
            positive += np.maximum(0, values)
            negative += np.minimum(0, values)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set(
            xticks=range(len(selected)),
            xticklabels=selected,
            title=case,
            ylabel="Cost at evaluation GPS minus blind endpoint",
        )
        ax.tick_params(axis="x", rotation=30)
    axes[-1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUTPUT / "GPS_cost_drivers.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    for case in CASES:
        base = next(
            r for r in final if r["case"] == case and r["variant"] == "normal" and r["arm"] == "c0"
        )
        data = [
            r
            for r in final
            if r["case"] == case
            and r["arm"] == "c0"
            and not r["generalized_score"]
            and r["variant"] != "normal"
        ]
        ax.scatter(
            [r["full_score"] - base["full_score"] for r in data],
            [r["position_error_km"] - base["position_error_km"] for r in data],
            label=case[-3:],
        )
    ax.axhline(0, color="black", linestyle="--")
    ax.axvline(0, color="black", linestyle="--")
    ax.set(
        xlabel="Change in normalized -2 ELBO versus normal (negative is better)",
        ylabel="Change in position error (km; negative is better)",
        title="Proper likelihood variants only; generalized scores excluded",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT / "score_vs_position.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for variant, style in [("rf_time_0p5", "o-"), ("rf_time_2", "s--")]:
        for rx in range(2):
            data = [details[f"{case}/{variant}/c0"] for case in CASES]
            mean = [d["state_additions"]["receiver_RF_rate_hz_s_ghz"][rx] for d in data]
            sigma = [d["receiver_RF_rate_conditional_sigma"][rx] for d in data]
            ax.errorbar(
                np.arange(5) + (rx - 0.5) * 0.08,
                mean,
                yerr=sigma,
                fmt=style,
                label=f"{variant}, RX{rx + 1}",
                capsize=3,
            )
    ax.set(
        xticks=range(5),
        xticklabels=[c[-3:] for c in CASES],
        ylabel="RF-contrast rate (Hz/s/GHz)",
        title="Conditional variational scales; not clock ground truth",
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "receiver_RF_rates.png", dpi=150)
    plt.close(fig)


def run():
    rows, details, ablations, bindings = [], {}, [], {}
    for case in CASES:
        directory = OUTPUT / "evaluation" / case
        part = json.loads((directory / "summary.json").read_text())
        if len(part) != len(SPECS) * 6:
            raise ValueError(f"incomplete evaluated scan: {case}: {len(part)}")
        rows.extend(part)
        ablations.extend(json.loads((directory / "c_ablation.json").read_text()))
        details.update(
            {
                case + "/" + key: value
                for key, value in json.loads((directory / "details.json").read_text()).items()
            }
        )
        bindings.update(json.loads((directory / "bindings.json").read_text()))
    final = [r for r in rows if r["final"]]
    selection = []
    for case in CASES:
        options = [
            r
            for r in final
            if r["case"] == case and r["arm"] == "c0" and not r["generalized_score"]
        ]
        best = min(options, key=lambda r: r["full_score"])
        partner = next(
            r
            for r in final
            if r["case"] == case and r["arm"] == "fitted_c" and r["variant"] == best["variant"]
        )
        selection.append(
            dict(
                case=case,
                variant=best["variant"],
                error_c0_km=best["position_error_km"],
                error_fitted_c_km=partner["position_error_km"],
            )
        )
    write(OUTPUT / "evaluation_summary.json", rows)
    dump_csv(OUTPUT / "evaluation_summary.csv", rows)
    write(OUTPUT / "frequency_details.json", details)
    write(OUTPUT / "c_ablation.json", ablations)
    dump_csv(OUTPUT / "c_ablation.csv", ablations)
    write(OUTPUT / "evaluation_bindings.json", bindings)
    write(OUTPUT / "c0_proper_model_selection.json", selection)
    figures(rows, details)
    positions = [
        "| Model | S01 | S02 | S03 | S04 | S05 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    coverage = [
        "| Model, fitted c | Accepted curved points | % curved | Curves | Points/curve | "
        "Common RMS c0 / fitted c (Hz) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in SPECS:
        pairs = [
            [
                next(
                    r for r in final if r["case"] == c and r["variant"] == variant and r["arm"] == a
                )
                for a in ["c0", "fitted_c"]
            ]
            for c in CASES
        ]
        tag = " †" if pairs[0][0]["generalized_score"] else ""
        positions.append(
            "| "
            + variant
            + tag
            + " | "
            + " | ".join(
                f"{a['position_error_km']:.3f} / {b['position_error_km']:.3f}" for a, b in pairs
            )
            + " |"
        )
        n = sum(b["white_gate_points"] for a, b in pairs)
        curves = sum(b["white_gate_curves"] for a, b in pairs)
        controls = [r for r in ablations if r["variant"] == variant]
        common = sum(r["common_points"] for r in controls)
        rms = [
            np.sqrt(
                sum(r[f"native_rms_{a}_hz"] ** 2 * r["common_points"] for r in controls)
                / max(1, common)
            )
            for a in ["c0", "fitted_c"]
        ]
        coverage.append(
            f"| {variant}{tag} | {n:,} | {100 * n / 12724:.2f}% | {curves} | "
            f"{n / max(1, curves):.2f} | {rms[0]:.3f} / {rms[1]:.3f} |"
        )
    selection_text = "; ".join(
        f"{r['case'][-3:]} {r['variant']} ({r['error_fitted_c_km']:.3f} km)" for r in selection
    )
    unconverged = [r for r in final if r["final_log_precision_change"] >= 1e-5]
    precision_checks = json.loads((OUTPUT / "precision_convergence_checks.json").read_text())
    maximum_precision_mean_change = max(
        (r["native_mean_RMS_change_hz"] for r in precision_checks), default=0
    )
    maximum_precision_cost_change = max(
        (abs(r["cost_change"]) for r in precision_checks), default=0
    )
    errors = [
        r["exact_orbit_mean_rms_hz"] for r in final if r["exact_orbit_mean_rms_hz"] is not None
    ]
    text = f"""# DSX01: prior bias, satellite corrections and receiver clock models

**The uniform independent all-five sub-1 km goal remains open.** Looser
Gaussian nuisance priors bring S03 to approximately **0.971 km**, but worsen
S04 and S05. Other models improve individual scans. Their lowest GPS errors
cannot be assembled into a valid blind method. This report follows the
[previous radio/orbit controls](../2026_10_18_dsx01_radio_orbit_followup/README.md).

## Experiments and controls

All **12,724 original curved observations** remain in each fit. Candidate
labels, integer aliases, causal TLE inputs and measured per-point radio noise
are fixed. Only curved evidence calibrates hardware. Linear-track transfer
was not rerun. No observations are held out and no RF was collected.

Each scan starts from the **25 × 25 km Mill Valley box**, centered at
37.906°, −122.545°, with 25 grid nodes, three shared c0-selected starts,
24 bounded iterations per start/arm, and three phase-reference rounds.
Every c0 / fitted-c pair has matching data, labels, aliases, other priors,
likelihood powers and search budgets. Global constant RF coefficient c is
distinct from the new satellite offsets and receiver RF/time terms. The known
coordinate 37.849061591561885°, −122.48574968092912° enters only evaluation.
Scans remain independent. This is exploratory development on the same corpus.

The initial three remedies are:

1. **Shared satellite frequency offsets.** One RF-scaled nuisance per
   supported family at sigma 3,000 Hz, or a variance-preserving shared/independent
   hierarchy. The latter keeps each fragment's constant variance at 1,000² Hz²
   and puts 90% of that budget into a shared component at 12.5 GHz. Only
   candidates with two RX/channel owners receive these added corrections.
2. **Heavier-tailed orbital priors.** One Normal/Gamma precision per satellite
   phase and three physical modes, using degrees 4 or 8. Marginal variances
   match the Gaussian control. These priors are more concentrated near zero;
   the comparison changes both central shape and tails, not only tail behavior.
3. **Family balance.** Fixed likelihood powers cap each satellite family's
   effective contribution at 100 or 50 points. No power is zero. These are
   generalized scores; comparing their raw totals with different power designs
   would be invalid. Family size alone proves insufficient as a reliability rule.

Followups target the observed failures. A normalized radio polynomial
background, marginalizing degrees 1–4, identifies 3/2/2/3/0 doubtful fragments
on S01–S05, covering 97/52/75/113/0 points. Their conditional evidence at the
completed normal c0 endpoint defines fixed calibration powers with a 0.01
floor. This is a heuristic reliability transfer, not final association
probability or exact mixture EM. Original acceptance gates remain unchanged.

Small satellite-specific frequency rates use sigma 0.25 or 1 Hz/s and remain
shared across RX/channels. Gaussian phase/bias controls separately widen
phase by 3 and fragment-bias sigma from 1,000 to 5,000 Hz; `weak_3` additionally
widens RX smooth and physical modes by 3. Hardware linear priors remain unchanged.

Native-Hz nonlinear radio models test a different assumption: heterodyne LO
frequency changes can be additive within a band, whereas fractional-reference
errors scale with RF. We compare native per-RX, independent native per-band,
and a mixed native/fractional per-RX process. All retain the same time basis
with no affine component on the scan interval. The gate adapter includes the
actual native calibration exactly once.

Finally, the earlier RF-times-time hypothesis is transferred into this joint
model with corrected RX mean-drift priors and GLRT-300 point noise. It adds
two receiver terms `(RF−band mean RF)/GHz × (time−150)` at sigma 0.5 or 2
Hz/s/GHz. This mechanism was tested earlier in a different nuisance model;
it is not claimed as a newly discovered correction.

## Independent position results

Errors are km, **c0 / fitted c**. A dagger marks a generalized weighting
design whose raw score must not compete with differently weighted designs.

{chr(10).join(positions)}

![All matched position comparisons](position_errors.png)

A single c0 selection rule, restricted to proper likelihood variants and using
the fully normalized variational bound, selects **{selection_text}**. Different
bound tightness and unverified satellite labels still limit its interpretation;
this is not calibrated model probability and does not use GPS to choose models.

## What drives the displaced solutions?

The previous S03 result already showed that calibration/constant priors can
favor a displaced site even when the true coordinate has lower weighted
frequency error. The widened-prior controls move S03 below 1 km, while the
same change worsens other scans. Thus weakening regularization is not a uniform
fix. Family caps and conditional reliability weights also have different
effects across scans; S05 contains no fragments favored by this polynomial
background diagnostic.

![Cost contributions at true coordinate versus blind minima](GPS_cost_drivers.png)

![Bound improvement versus position improvement](score_vs_position.png)

The RF/time coefficients below are relative calibration parameters, with
variational scales conditional on the fitted position and labels. They do not
establish whether a physical clock, LNB or model discrepancy caused the term.

![Receiver RF-rate terms and conditional scales](receiver_RF_rates.png)

Exact combined SGP4 mean checks, after adding back the same auxiliary
frequency terms, range up to **{max(errors):.3f} Hz RMS** across completed
endpoints. They check means, not exact nonlinear marginalization or identity.
There are **{sum(r['exact_orbit_check_error'] is not None for r in final)} unavailable
exact-mean checks**, with reasons recorded in the evaluation table.
There are **{len(unconverged)} final arms** above the 1e-5 latent-precision
change tolerance at the 256-iteration limit; the
[convergence receipt](precision_convergence_checks.json) records the
fixed-endpoint tighter checks separately.
Those checks change the conditional means by at most
**{maximum_precision_mean_change:.4f} Hz RMS** and the bound by
**{maximum_precision_cost_change:.3g}** units. This iteration limit is not the
main source of the kilometre-scale displacement at those endpoints.

## Coverage and frequency fit

The original white-residual gates and the 12,724 curved-point denominator are
used throughout. These are nominated curved fragments, not all raw GLRT
associations. RMS uses common accepted points within each matched c pair.
Position accuracy is evaluated separately from fit and coverage.

{chr(10).join(coverage)}

## Numerical and literature grounding

The grouped Normal/Gamma implementation restores likelihood and prior
normalization constants. It reproduces the previous Gaussian control and is
checked against independent one-dimensional quadrature, including the exact
projection of a shared three-dimensional Student prior, unit prior variances,
fractional-likelihood integrals and
monotone coordinate updates. The hierarchy extends the variational framework
described by [Tipping and Lawrence](https://inverseprobability.com/publications/files/robustBayesian.pdf).
The fixed-power experiments use a loss-based update of the kind formalized by
[Bissiri, Holmes and Walker](https://arxiv.org/abs/1306.6430); that framework
does not by itself calibrate our weights or validate localization accuracy.

There are **{len(rows)} saved fit records / {len(rows) // 2} matched c pairs**,
including every outer round. [Evaluation CSV](evaluation_summary.csv),
[common-point c controls](c_ablation.csv), [gate/cost details](frequency_details.json),
and [input bindings](evaluation_bindings.json) separate fit from position.
Production contracts and golden scientific fixtures are unchanged. GLRT-300
means 300 pilot symbols per frame from archived 2.5 MS/s, 20 ms windows.

The next analysis should add information rather than choose per-scan GPS
winners: securely transfer linear detections for geometry while retaining
curved-only calibration, transfer timing-linked frequency-bias covariance into
the current joint model, and test variational branch sensitivity on S05.
"""
    checkpoint = ROOT / "reports/2026_10_18_dsx01_prior_bias_iterations"
    paths = [
        checkpoint / name
        for name in ["source_manifest.json", "input_manifest.json", "frozen_tests.json"]
    ]
    if all(p.exists() for p in paths):
        sources, inputs, tests = [json.loads(p.read_text()) for p in paths]
        passed = re.search(r"(\d+) passed", tests["stdout"])
        text += (
            f"\nFrozen verification: **{passed[1]} passing tests**, "
            f"**{sources['count']} source snapshots**, and **{inputs['count']} pinned inputs**. "
            "See [validation](validation.json), [test receipt](frozen_tests.json), "
            "[source hashes](source_manifest.json), [input hashes](input_manifest.json) "
            "and [product replay](frozen_endpoint_replay.json).\n"
        )
    (OUTPUT / "README.md").write_text(text)
    print(
        json.dumps(dict(records=len(rows), matched_pairs=len(rows) // 2, selection=selection)),
        flush=True,
    )


if __name__ == "__main__":
    run()
