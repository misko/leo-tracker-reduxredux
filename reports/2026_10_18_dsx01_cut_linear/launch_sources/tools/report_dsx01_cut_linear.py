"""Evaluate blind linear-transfer searches without feeding GPS into inference."""

import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from dsx01_cut_linear import curve_posterior, transfer_design
from localize_merged_track_catalogue import distance_km
from probe_dsx01_cut_linear import OUTPUT, VARIANTS, CutScore, prepare
from report_dsx01_joint_marginal import EvaluationAdapter, dump_csv
from report_dsx01_model_iterations import REFERENCE, nominated_metrics

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD, profile

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def linear_metrics(p, x, selected):
    result, _ = curve_posterior(p, x)
    rows = []
    for row in selected:
        i = row["index"]
        t = p.scan.tracks[i]
        intercept, design, elevation = transfer_design(p, t, row["candidate_index"], x)
        predicted = intercept + design @ result["coefficient"]
        terms = profile(t["values"] + row["alias"] * PERIOD, predicted, p.scan.white[i][0])
        noise = batch_noise_screen(terms["innovations"], t["times"])
        passed = bool(
            noise["noise_screen_pass"][0]
            and terms["rms"][0] <= 450
            and abs(terms["bias"][0]) <= 3000
            and terms["alias"][0] == 0
            and elevation.min() >= 0
        )
        rows.append(
            dict(
                component=t["key"],
                points=len(t["times"]),
                candidate_index=row["candidate_index"],
                norad=row["norad"],
                compatible=passed,
                native_square_hz2=float(np.sum(terms["residual"][0] ** 2)),
                rms_hz=float(terms["rms"][0]),
                bias_hz=float(terms["bias"][0]),
                noise={k: v[0] for k, v in noise.items()},
            )
        )
    return rows


def curved_metrics(p, parent, x):
    fit = dict(parent, east_north_km=x, fits=[dict(parameters=x, score=0.0)])
    adapter = EvaluationAdapter(p)
    return nominated_metrics(
        p.scan,
        dict(fit=fit, method="receiver_smooth", arm="fitted_c" if p.fitted_c else "c0"),
        problem_factory=lambda *args: adapter,
    )


def run():
    summaries, details, bindings = [], {}, {}
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        scan, parent, problems, nominations, source = prepare(case)
        directory = OUTPUT / case
        paths = [
            directory / name
            for name in ["endpoints.json", "protocol.json", "nominations.json", "diagnostic.json"]
        ]
        paths.append(source)
        bindings.update({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        fits = json.loads((directory / "endpoints.json").read_text())
        if set(fits) != set(VARIANTS):
            raise ValueError(f"incomplete fits: {case}")
        for variant, arms in [("baseline", parent), *fits.items()]:
            for arm, fit in arms.items():
                p = problems[arm]
                x = np.asarray(fit["parameters"])
                curved = curved_metrics(p, parent[arm], x)
                score = CutScore(p, nominations, "joint" if variant == "baseline" else variant)
                selected = [] if variant == "baseline" else score.selected
                linear = linear_metrics(p, x, selected)
                # Corrections continue to require two accepted curved owners.
                owners = {}
                for r in curved["tracks"]:
                    if r["compatible"]:
                        t = next(t for t in scan.tracks if t["key"] == r["component"])
                        owners.setdefault(r["candidate_index"], set()).add(
                            (t["receiver"], t["channel"])
                        )
                for r in linear:
                    r["compatible"] = (
                        r["compatible"] and len(owners.get(r["candidate_index"], set())) >= 2
                    )
                key = f"{case}/{variant}/{arm}"
                details[key] = dict(curved=curved, linear=linear)
                result = p.calculate(x)
                replay = (
                    None if variant == "baseline" else abs(score.score(x)["total"] - fit["score"])
                )
                if replay is not None and replay > 1e-6:
                    raise ValueError(f"endpoint replay failure:{key}:{replay}")
                n = sum(r["points"] for r in linear)
                accepted = [r for r in linear if r["compatible"]]
                na = sum(r["points"] for r in accepted)
                summaries.append(
                    dict(
                        case=case,
                        variant=variant,
                        arm=arm,
                        position_error_km=distance_km(
                            (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                        ),
                        curved_points=len(p.values),
                        linear_nominated_points=n,
                        linear_white_gate_points=na,
                        linear_white_gate_tracks=len(accepted),
                        linear_white_gate_rms_hz=float(
                            np.sqrt(sum(r["native_square_hz2"] for r in accepted) / max(1, na))
                        ),
                        curved_white_gate_points=curved["accepted_nominated_curved_points"],
                        curved_white_gate_rms_hz=curved["accepted_native_rms_hz"],
                        all_curved_conditional_rms_hz=float(
                            np.sqrt(np.mean(result["conditional_residual_hz"] ** 2))
                        ),
                        objective_replay_error=replay,
                        selected_attempt_converged=fit.get("converged"),
                    )
                )
    ablations = []
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        for variant in ["baseline", *VARIANTS]:
            pair = [details[f"{case}/{variant}/{arm}"] for arm in ["c0", "fitted_c"]]
            populations = [d["curved"]["tracks"] + d["linear"] for d in pair]
            common = set.intersection(
                *[
                    {r["component"] for r in population if r["compatible"]}
                    for population in populations
                ]
            )
            row = dict(case=case, variant=variant)
            for arm, population in zip(["c0", "fitted_c"], populations, strict=True):
                selected = [r for r in population if r["component"] in common]
                n = sum(r["points"] for r in selected)
                row["common_points"] = n
                row[f"native_rms_{arm}_hz"] = float(
                    np.sqrt(sum(r["native_square_hz2"] for r in selected) / max(1, n))
                )
            ablations.append(row)
    write(OUTPUT / "c_ablation.json", ablations)
    dump_csv(OUTPUT / "c_ablation.csv", ablations)
    write(OUTPUT / "evaluation_summary.json", summaries)
    write(OUTPUT / "frequency_details.json", details)
    write(OUTPUT / "evaluation_bindings.json", bindings)
    dump_csv(OUTPUT / "evaluation_summary.csv", summaries)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    variants = ["baseline", *VARIANTS]
    for ax, arm in zip(axes, ["c0", "fitted_c"], strict=True):
        a = np.array(
            [
                [
                    next(
                        r["position_error_km"]
                        for r in summaries
                        if r["case"] == f"DSX01-S0{k}" and r["variant"] == v and r["arm"] == arm
                    )
                    for k in range(1, 6)
                ]
                for v in variants
            ]
        )
        im = ax.imshow(a, vmin=0, vmax=2, cmap="YlOrRd", aspect="auto")
        ax.set_xticks(range(5), [f"S0{k}" for k in range(1, 6)])
        ax.set_yticks(range(4), variants)
        ax.set_title(arm)
        for (i, j), value in np.ndenumerate(a):
            ax.text(j, i, f"{value:.3f}", ha="center", va="center")
    fig.colorbar(im, ax=axes, label="Independent position error (km)", fraction=0.025, pad=0.04)
    fig.savefig(OUTPUT / "position_errors.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    lines = [
        "# DSX01: linear geometry with calibration from curved tracks",
        "",
        "**The independent all-five sub-1 km goal remains open.** These prototypes add "
        "information from previously unused shorter or near-linear graph fragments. "
        "Calibration at every trial position uses the original curved observations only. "
        "Satellite identities remain hypotheses.",
        "",
        "The baseline is the previous per-point-noise Gaussian-prior control. Three transfer "
        "variants use: (1) joint predictive covariance and a 1,000 Hz independent fragment "
        "offset; (2) a 1,000,000 Hz offset to nearly remove constant-frequency information; "
        "(3) only same RX/channel continuations within 10 seconds. Shared calibration "
        "uncertainty is integrated jointly across the new fragments. A factorized "
        "variational curved posterior is approximated as Gaussian for prediction; this "
        "is a modular research score, not an exactly marginalized joint posterior or "
        "calibrated probability.",
        "",
        "Each search uses the 25 × 25 km Mill Valley box, 25 grid nodes, three starts "
        "chosen by c0 and shared with fitted c, and at most 24 bounded iterations per "
        "start. Candidate labels, aliases and nominated fragments are frozen at the "
        "previous blind c0 endpoint. All original curved observations remain. Linear "
        "measurements retain their original CFO and 150 Hz noise; they were not GLRT-300 "
        "remeasured. No observations are withheld. Evaluation GPS is used only after "
        "nomination and search. The phase reference is frozen from the preceding blind "
        "three-round curved search.",
        "",
        "Nominations require a curved-supported receiver/band, a satellite with two "
        "accepted curved RX/channel owners, positive elevation, signal/background log "
        "odds ≥ log(99), and a best/runner-up identity log margin ≥ log(10). These "
        "conditional selection rules are exploratory and are not identity probabilities. "
        "The familiar residual, RMS, offset, alias and ownership gates are evaluated "
        "separately below; nomination alone is not an accepted association.",
        "",
        "| Method | S01 | S02 | S03 | S04 | S05 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in variants:
        values = []
        for k in range(1, 6):
            pair = [
                next(
                    r
                    for r in summaries
                    if r["variant"] == variant and r["case"] == f"DSX01-S0{k}" and r["arm"] == arm
                )
                for arm in ["c0", "fitted_c"]
            ]
            values.append(" / ".join(f"{r['position_error_km']:.3f}" for r in pair))
        lines.append("| " + variant + " | " + " | ".join(values) + " |")
    lines += [
        "",
        "Errors are km, **c0 / fitted c**.",
        "",
        "![Position errors](position_errors.png)",
        "",
        "The new evidence improves S05 but worsens S02 and S03. At the old S05 c0 "
        "endpoint, the joint predictive linear score favors evaluation GPS by 12.03 "
        "units, outweighing the 10.12-unit curved-score preference for the displaced "
        "endpoint. S03 linears instead reinforce displacement. Those GPS comparisons "
        "diagnose behavior; they do not choose nominations, parameters or winners.",
        "",
        "| Fitted-c method | Nominated linear points | Linear points passing all gates "
        "| Curved points passing gates | Curved accepted RMS (Hz) | Linear accepted RMS (Hz) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in variants:
        rr = [r for r in summaries if r["variant"] == variant and r["arm"] == "fitted_c"]
        cn = sum(r["curved_white_gate_points"] for r in rr)
        ln = sum(r["linear_white_gate_points"] for r in rr)
        cr = np.sqrt(
            sum(r["curved_white_gate_rms_hz"] ** 2 * r["curved_white_gate_points"] for r in rr)
            / max(1, cn)
        )
        lr = np.sqrt(
            sum(r["linear_white_gate_rms_hz"] ** 2 * r["linear_white_gate_points"] for r in rr)
            / max(1, ln)
        )
        lines.append(
            f"| {variant} | {sum(r['linear_nominated_points'] for r in rr):,} "
            f"| {ln:,} | {cn:,} | {cr:.2f} | {lr:.2f} |"
        )
    lines += [
        "",
        "Frequency fit and position accuracy are distinct results. Accepted populations "
        "can differ; RMS here is descriptive, not a matched-population gain claim. "
        "[Common-population c controls](c_ablation.csv) retain both arms' shared points.",
        "",
        "[Evaluation table](evaluation_summary.csv), "
        "[frequency and residual gates](frequency_details.json), "
        "[input bindings](evaluation_bindings.json).",
        "",
        "The separation between geometry evidence and reported calibration is motivated "
        "by [modular inference and cutting feedback](https://arxiv.org/abs/2211.03274). "
        "This implementation uses its own conditional-predictive approximation; the "
        "cited framework does not validate our satellite identities or uncertainty scales.",
        "",
    ]
    (OUTPUT / "README.md").write_text("\n".join(lines))
    print(
        json.dumps(
            dict(
                records=len(summaries),
                max_endpoint_replay_error=max(r["objective_replay_error"] or 0 for r in summaries),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    run()
