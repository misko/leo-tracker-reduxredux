"""Render post-seal predictive comparisons without new objectives or fitting."""

import json
import sys

import matplotlib
import numpy as np
import qualify as source

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = source.HERE


def render(write_report=True):
    value = source.read(HERE / "evaluation.json")
    results, blocks = value["results"], value["blocks"]
    fitted_old, fitted_new = results["independent_fitted-c"], results["automatic_fitted-c"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for index, arm in enumerate(("fitted-c", "zero-c")):
        selected = [r for r in blocks if r["arm"] == arm]
        axis = axes[0, index]
        delta = [r["delta_new_singleton_nll"] for r in selected]
        axis.bar(
            [r["start_s"] for r in selected],
            delta,
            width=14,
            color=["#24806b" if d < 0 else "#bb594c" for d in delta],
        )
        axis.axhline(0, color="black", lw=0.7)
        axis.set(
            title=arm + ": coherent minus independent",
            xlabel="Held block start (s)",
            ylabel="New singleton predictive NLL change",
        )
        axis = axes[1, index]
        names = ("independent_" + arm, "automatic_" + arm)
        for offset, label in enumerate(("original_shared", "new_singleton")):
            counts = [results[n][label]["held"]["associated"] for n in names]
            axis.bar(
                np.arange(2) + (offset - 0.5) * 0.32,
                counts,
                width=0.32,
                label="Original shared" if offset == 0 else "New latent singleton",
            )
        axis.set(
            xticks=[0, 1],
            xticklabels=["Independent", "Coherent"],
            ylabel="Assigned / 1909 held observations",
            title=arm + ": distinct classifiers",
        )
        axis.legend(fontsize=8)
    fig.savefig(HERE / "held_predictive_comparison.png", dpi=160)
    plt.close(fig)
    states = source.read(HERE / "state_diagnostics.json")["rows"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    names = [r["case"].replace("automatic", "coherent") for r in states]
    axis = axes[0, 0]
    axis.bar(np.arange(4), [r["configured_reference_distance_km"] for r in states], color="#5a7ca3")
    for index, r in enumerate(states):
        axis.scatter(
            index,
            r["configured_reference_distance_km"],
            color="black",
            marker="o" if r["strict_audit"]["accepted"] else "x",
            zorder=3,
        )
    axis.set(
        xticks=np.arange(4),
        xticklabels=names,
        ylabel="Configured distance (km)",
        title="Post-seal location diagnostic (o strict, x nonstrict)",
    )
    axis.tick_params(axis="x", rotation=25)
    q_bins = np.linspace(0, max(max(r["q"]) for r in states) * 1.05, 25)
    for r in states:
        label = r["case"].replace("automatic", "coherent")
        axes[0, 1].hist(
            r["relative_timing_s"],
            bins=np.arange(-24, 26, 2),
            histtype="step",
            label=f"{label}; common {r['common_timing_s']:.2f}s",
        )
        axes[1, 0].hist(r["q"], bins=q_bins, histtype="step", label=label)
    axes[0, 1].set(
        xlabel="Relative candidate timing (s)",
        ylabel="Candidates (45 per state)",
        title="Unchanged 2s relative / 3s common priors",
    )
    axes[0, 1].legend(fontsize=7)
    axes[1, 0].set(
        xlabel="Full-bank detection q",
        ylabel="Candidates (45 per state)",
        title="Learned q, total budget 1.6",
    )
    axes[1, 0].legend(fontsize=7)
    for rx in range(2):
        axes[1, 1].bar(
            np.arange(4) + (rx - 0.5) * 0.32,
            [r["band_update_from_complete_seed_hz"][rx] / 1000 for r in states],
            width=0.32,
            label=f"RX{rx + 1} (native {rx}) high-band constant",
        )
    axes[1, 1].set(
        xticks=np.arange(4),
        xticklabels=names,
        ylabel="Update from common seed (kHz)",
        title="Free receiver-band constants",
    )
    axes[1, 1].tick_params(axis="x", rotation=25)
    axes[1, 1].legend(fontsize=7)
    fig.savefig(HERE / "state_parameter_comparison.png", dpi=160)
    plt.close(fig)
    if not write_report:
        return
    lines = [
        "# Fixed-partition coherent pilot: blocked S03",
        "",
        "The following is one TRAIN-only blocked interpolation pilot, not an all-five "
        "or production result. The fitted-c broadening gate is **"
        + ("passed" if value["gate"]["passed"] else "not passed")
        + "**. "
        "No held measurement selected an endpoint, parameter, partition or hyperparameter.",
        "",
        f"Fitted-c held singleton NLL changes {fitted_old['new_singleton']['held']['nll']:.3f} "
        f"to {fitted_new['new_singleton']['held']['nll']:.3f}; lower is better. "
        f"Only {value['gate']['improved_blocks']}/7 blocks improve. The coherent fitted endpoint "
        "is nonstrict. These mixed/negative outcomes do not authorize an all-five expansion.",
        "",
        "| Policy | c arm | Strict KKT | Calls | Held new singleton NLL | Original shared NLL | "
        "Original classifier held / 1909 | Requested held / 80 | New latent held / 1909 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, r in results.items():
        policy, arm = key.split("_", 1)
        diag, audit = r["diagnostics"], r["audit"]
        lines.append(
            f"| {policy} | {arm} | {audit.get('stationarity', 'unavailable')} "
            f"({audit['accepted']}) | {diag['evaluations']} | "
            f"{r['new_singleton']['held']['nll']:.3f} | "
            f"{r['original_shared']['held']['nll']:.3f} | "
            f"{r['original_shared']['held']['associated']} | "
            f"{r['original_shared']['requested_held']['associated']} | "
            f"{r['new_singleton']['held']['associated']} |"
        )
    lines += ["", "Gate details: `" + json.dumps(value["gate"], sort_keys=True) + "`.", ""]
    for arm in ("fitted-c", "zero-c"):
        current = results["automatic_" + arm]
        for label in ("original_shared", "new_singleton"):
            m = current[label]["held"]
            lines += [
                f"{arm}, {label}: {m['new']} new, {m['lost']} lost, {m['retained']} retained. "
                f"On the same retained intersection RMS changes "
                f"{m['intersection_baseline_rms_hz']} to {m['intersection_current_rms_hz']} Hz. "
                f"The overall associated RMS is {m['associated_rms_hz']} Hz; "
                "its selected population differs.",
                "",
            ]
    lines += [
        "",
        "Requested held windows remain evaluation-only and are never linking labels:",
        "",
        "| State | Window | Original classifier / N | New latent classifier / N |",
        "|---|---|---:|---:|",
    ]
    for case, row in results.items():
        for rid, item in row["original_shared"]["windows"].items():
            old = item["held"]
            new = row["new_singleton"]["windows"][rid]["held"]
            lines.append(
                f"| {case} | {rid} | {old['associated']}/{old['observations']} | "
                f"{new['associated']}/{new['observations']} |"
            )
    lines += [
        "The exact four endpoints and then all four metadata-only predictions were sealed "
        "before held CFO scoring. TRAIN has2073 rows; HELD has1909 and the boundary has6. "
        "Requested HELD has80 points. The other555 requested points from the other four "
        "sources are untested here. No missing or unassigned point leaves a denominator.",
        "",
        "Both policies use the same complete original public TRAIN seed,45 original candidates, "
        "free receiver-band constants and unchanged physical/q/clock/timing priors. "
        "c0 changes and fixes only the RF coefficient, conditional on fitted-c upstream discovery. "
        "Each refit has1000 actual calls/120 active seconds; one independent endpoint audit "
        "is a separately counted call. The broad regional research domain is used; the original "
        "production25km local disk is not imposed. Nonstrict results remain present and never "
        "become accepted by a relaxed threshold.",
        "",
        "Automatic TRAIN-only450Hz/45s/24point segmentation produces a response-selected "
        "partition. Its selection likelihood is omitted: this is a normalized fixed-partition "
        "working likelihood, not a Bayes factor or proof of common emitters. HELD rows use "
        "only the proper new singleton marginal, with no held grouping. The original shared "
        "normalized density/classifier is reported separately. These are model associations, "
        "not verified satellite identities. Reference location entered only the separate post-seal "
        "diagnostic, never grouping, fitting, endpoint selection or the predictive gate.",
        "",
        "`QUALIFICATION.md` records930 zero-fit objective checks plus8 metadata predictors. "
        "`evaluation.json` retains both scores, all roles/windows, block deltas and the gate; "
        "the evaluation NPZs retain per-point classifications and singleton NLLs. Raw training "
        "coherent groups have no invented per-row NLL. Better training fit alone establishes "
        "no geographic improvement.",
        "",
        "![Paired held predictive results](held_predictive_comparison.png)",
        "",
        "The original cold TRAIN terminal's795/1909 held assignments is a descriptive anchor "
        "from a different kernel and less continuation, not this pilot's matched causal control. "
        "The matched comparison uses both policies with the same singleton density. "
        "The configured station reference is operator-supplied; survey uncertainty is unknown. "
        "Position is reported independently of the predictive gate.",
        "",
        "| State | Configured distance km | Common timing s | Relative timing RMS s | "
        "Inside original25km disk | Broad research feasible/strict |",
        "|---|---:|---:|---:|---|---|",
        *[
            f"| {r['case']} | {r['configured_reference_distance_km']:.6f} | "
            f"{r['common_timing_s']:.6f} | {r['relative_timing_rms_s']:.6f} | "
            f"{r['inside_old_production25km_disk']} | "
            f"{r['strict_audit']['feasible']}/{r['strict_audit']['accepted']} |"
            for r in states
        ],
        "",
        "![Post-seal position and complete parameter summaries](state_parameter_comparison.png)",
        "",
        "The prespecified automatic linking and coherent working likelihood did not improve the "
        "fitted-c held forecasts in this pilot. The c0 full-count gain also loses requested-window "
        "coverage and has a nonstrict independent control, so it does not reverse that conclusion. "
        "This rejects broadening this fixed pilot policy; it does not establish that all temporal "
        "association models fail. No extra fitting, endpoint repair, threshold change "
        "or alternative grouping was used after these outcomes.",
    ]
    with (HERE / "README.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")


def seal():
    for name in ("README.md", "evaluation.json", "state_diagnostics.json"):
        if not (HERE / name).is_file():
            raise ValueError("Complete report required before final seal")
    files = [
        dict(path=str(p.relative_to(HERE)), sha256=source.digest(p))
        for p in sorted(HERE.rglob("*"))
        if p.is_file() and p.name != "FINAL_SEAL.json"
    ]
    source.save(
        HERE / "FINAL_SEAL.json",
        dict(
            files=files,
            sealed=True,
            scope="Single blocked S03 pilot; no new corpus campaign",
            original_anchor_sha256=source.digest(HERE.parent / "original_anchor/summary.json"),
            original_anchor_manifest_sha256=source.digest(
                HERE.parent / "original_anchor/manifest.json"
            ),
        ),
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["seal"]:
        seal()
    elif sys.argv[1:] == ["plots"]:
        render(write_report=False)
    elif not sys.argv[1:]:
        render()
    else:
        raise ValueError("Use no arguments to render, plots for figures, or seal after review")
