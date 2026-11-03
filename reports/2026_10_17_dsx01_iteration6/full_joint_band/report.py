"""Plots and factual report from the globally sealed all-five evaluation."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCES = ("S01", "S02", "S03", "S04", "S05")
COLORS = {"original": "#777777", "fixed": "#2776b1", "joint": "#d77a26"}


def read(path):
    return json.loads(path.read_text())


def save_plot(fig, stem):
    for suffix in ("png", "pdf"):
        fig.savefig(HERE / f"{stem}.{suffix}", dpi=170, bbox_inches="tight")
    plt.close(fig)


def main():
    evaluation = read(HERE / "evaluation.json")
    rows, windows = evaluation["rows"], evaluation["windows"]
    original = {s: read(HERE / f"original_{s}.json") for s in SOURCES}
    window_ids = sorted({w["window"] for w in windows})
    for arm in ("fitted-c", "zero-c"):
        fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
        x = np.arange(15)
        first = [
            next(
                w
                for w in windows
                if w["arm"] == arm and w["method"] == "fixed" and w["window"] == window
            )
            for window in window_ids
        ]
        axes[0].bar(
            x - 0.25,
            [w["original_assigned"] for w in first],
            0.23,
            color=COLORS["original"],
            label="Original fitted-c production",
        )
        for method, offset in (("fixed", 0), ("joint", 0.25)):
            selected = [
                next(
                    w
                    for w in windows
                    if w["arm"] == arm and w["method"] == method and w["window"] == window
                )
                for window in window_ids
            ]
            axes[0].bar(
                x + offset,
                [w["assigned"] for w in selected],
                0.23,
                color=COLORS[method],
                label=method,
            )
            axes[1].plot(
                x,
                [100 * w["net_original_missing_restored_fraction"] for w in selected],
                "o-",
                color=COLORS[method],
                label=method,
            )
        axes[0].plot(
            x, [w["observations"] for w in first], "k_", markersize=12, label="Fixed original N"
        )
        axes[0].set_ylabel("Assigned original points")
        axes[0].legend(ncol=4, frameon=False)
        axes[1].axhline(80, linestyle=":", color=".4", label="Descriptive 80% net restoration")
        axes[1].set_ylabel("Net original missing restored (%)")
        axes[1].set_xticks(x, [w.replace("DSX01-", "") for w in window_ids])
        axes[1].set_xlabel("All 15 requested windows, all 693 original points")
        for ax in axes:
            ax.grid(axis="y", alpha=0.2)
        fig.suptitle(f"{arm}: complete fixed versus joint-band policies; no per-window selection")
        fig.tight_layout()
        save_plot(fig, f"windows_{arm}")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        values = sorted(r["configured_reference_distance_km"] for r in original.values())
        ax.step(
            values,
            np.arange(1, 6) / 5,
            where="post",
            color=COLORS["original"],
            label="Original production (saved local domains)",
        )
        ax.scatter(values, np.arange(1, 6) / 5, color=COLORS["original"], s=20)
        for method in ("fixed", "joint"):
            selected = sorted(
                [r for r in rows if r["arm"] == arm and r["method"] == method],
                key=lambda r: r["configured_reference_distance_km"],
            )
            values = [r["configured_reference_distance_km"] for r in selected]
            strict = sum(r["audit"]["accepted"] for r in selected)
            ax.step(
                values,
                np.arange(1, 6) / 5,
                where="post",
                color=COLORS[method],
                label=f"{method} ({strict}/5 strict)",
            )
            for i, r in enumerate(selected):
                ax.scatter(
                    values[i],
                    (i + 1) / 5,
                    color=COLORS[method],
                    marker="o" if r["audit"]["accepted"] else "x",
                    s=35,
                )
                ax.annotate(
                    r["source_id"],
                    (values[i], (i + 1) / 5),
                    xytext=(3, 4 if method == "joint" else -10),
                    textcoords="offset points",
                    fontsize=6,
                    color=COLORS[method],
                )
        ax.axvline(0.5, color=".4", linestyle=":", label="0.5 km goal")
        ax.set(
            xscale="log",
            xlabel="Configured-reference distance (km)",
            ylabel="Fraction of the same five sources",
            title=arm,
            ylim=(0, 1.05),
        )
        ax.legend(fontsize=7, frameon=False)
        ax.grid(alpha=0.2)
    fig.suptitle("Position diagnostic after all20 outcomes sealed; x = nonstationary selector")
    fig.tight_layout()
    save_plot(fig, "position_cdf")

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for col, arm in enumerate(("fitted-c", "zero-c")):
        for method in ("fixed", "joint"):
            selected = [r for r in rows if r["arm"] == arm and r["method"] == method]
            relative = np.concatenate([r["relative_timing_s"] for r in selected])
            total = np.concatenate([r["total_timing_s"] for r in selected])
            axes[0, col].hist(
                relative,
                bins=np.arange(-32, 33, 1),
                histtype="step",
                color=COLORS[method],
                label=method,
            )
            axes[1, col].hist(
                total,
                bins=np.arange(-21, 22, 1),
                histtype="step",
                color=COLORS[method],
                label=method,
            )
        axes[0, col].set(title=arm, xlabel="Relative timing offset (s)", ylabel="Candidate entries")
        axes[1, col].set(xlabel="Total timing offset (s)", ylabel="Candidate entries")
        axes[0, col].legend(frameon=False)
    fig.suptitle("Unchanged 2s relative / 3s common priors; same 215 candidate entries per policy")
    fig.tight_layout()
    save_plot(fig, "timing_distributions")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        for receiver, marker in ((0, "o"), (1, "s")):
            selected = [
                next(
                    r
                    for r in rows
                    if r["arm"] == arm and r["method"] == "joint" and r["source_id"] == s
                )
                for s in SOURCES
            ]
            ax.plot(
                SOURCES,
                [r["band_update_hz"][receiver] for r in selected],
                marker=marker,
                label=f"RX{receiver + 1}",
            )
        ax.axhline(0, color=".5", linewidth=0.8)
        ax.set(title=arm, ylabel="Joint high-band offset update (Hz)")
        ax.legend(frameon=False)
    fig.suptitle("Offsets share each source's fixed frame; coupled calibration, not hardware truth")
    fig.tight_layout()
    save_plot(fig, "band_updates")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    thresholds = np.linspace(0, 1000, 501)
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        for method in ("fixed", "joint"):
            numerator = np.zeros(len(thresholds), int)
            for s in SOURCES:
                with np.load(HERE / f"eval_{s}_{arm}_{method}.npz") as point:
                    selected = np.abs(point["residual_hz"][point["associated"]])
                    numerator += np.array([int(np.sum(selected <= t)) for t in thresholds])
            ax.plot(thresholds, numerator / 20084, color=COLORS[method], label=method)
        ax.set(
            title=arm,
            xlabel="Absolute residual threshold (Hz)",
            ylabel="Fraction of all 20,084 original observations",
            ylim=(0, 1),
        )
        ax.legend(frameon=False)
        ax.grid(alpha=0.2)
    fig.suptitle("Frequency support uses fixed all-point denominator; not localization accuracy")
    fig.tight_layout()
    save_plot(fig, "frequency_support")

    lines = [
        "# Full DSX01 joint-band policy gate",
        "",
        "The full-cohort gate is negative: fitted-c joint calibration raises whole-recording "
        "coverage13784→14144/20084 but requested coverage falls422→420/693, with strict "
        "endpoints4/5→3/5. Median configured-reference distance remains132.472→132.415km. "
        "The c0 comparison similarly gains whole-recording coverage12180→13412 while losing "
        "requested coverage417→399 and strict endpoints5/5→1/5. No geographic recovery or "
        "model promotion follows the better training fit.",
        "",
        "All20 outcomes and training-only selectors sealed before window or configured-position "
        "evaluation. One frozen policy applies to all five original candidate banks and all15 "
        "requested windows. No per-window/source choice, reference seeding, RF collection, held "
        "selection, original-label truth assumption or production change occurs.",
        "",
        "## Complete-policy aggregate",
        "",
        "| RF arm | Policy | Assigned/20084 | Requested/693 | New/lost vs original | "
        "Requested new/lost | Overall assigned RMS Hz | Selected strict | Raw strict | Calls |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for a in evaluation["aggregates"]:
        full, requested = a["full_vs_original"], a["requested_vs_original"]
        lines.append(
            f"| {a['arm']} | {a['method']} | {full['assigned']} | "
            f"{requested['assigned']} | {full['new']}/{full['lost']} | "
            f"{requested['new']}/{requested['lost']} | {full['associated_rms_hz']:.3f} | "
            f"{a['strict_selected']}/5 | "
            f"{a['strict_returned']}/5 | {a['charged_inference_calls']} |"
        )
    lines += [
        "",
        "Summed fitted-c data NLL improves222582.028→220244.221 (−2337.808), while c0 "
        "improves231857.131→225353.196 (−6503.935). These are in-sample likelihood changes, "
        "not evidence of improved localization or predictive generalization. Overall assigned "
        "RMS uses a changing population; the intersection RMS below uses exactly retained pairs.",
        "",
        "The original reference is the same saved fitted-c production outcome for both "
        "RF sensitivity arms. The c0 arm changes only the fitted-profile seed's c coordinate, "
        "and retains all other complete coordinates and constraints; upstream discovery and seed "
        "construction used fitted c. It is not an independent cold c0 pipeline.",
        "",
        "## Matched-policy effects and paired residuals",
        "",
        "| RF arm | Joint minus fixed full count | Joint new/lost vs fixed | Requested delta | "
        "Full intersection RMS fixed→joint Hz | Requested intersection RMS Hz |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for a in evaluation["aggregates"]:
        if a["method"] != "joint":
            continue
        f, q = a["full_vs_matched_fixed"], a["requested_vs_matched_fixed"]
        lines.append(
            f"| {a['arm']} | {f['new'] - f['lost']:+d} | {f['new']}/{f['lost']} | "
            f"{q['new'] - q['lost']:+d} | {f['intersection_original_rms_hz']:.3f}→"
            f"{f['intersection_current_rms_hz']:.3f} | "
            f"{q['intersection_original_rms_hz']:.3f}→{q['intersection_current_rms_hz']:.3f} |"
        )
    lines += [
        "",
        "## Every source and RF arm",
        "",
        "J is compared only within a target, and no lower-J feasible nonstationary point is "
        "silently filtered. Raw returned endpoints, profile seeds and original complete states "
        "remain in outcomes_seal.json. Selected labels and both strict flags expose selection "
        "or optimizer failures rather than claim they are model improvements.",
        "",
        "| Source | RF | Policy | Selected | J / data NLL | Full / requested | KKT | "
        "Configured km | Common timing s | q change RMS | RX band updates Hz |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['source_id']} | {r['arm']} | {r['method']} | {r['selected']} | "
            f"{r['objective']:.3f} / {r['likelihood_nll']:.3f} | "
            f"{r['full']['assigned']} / {r['challenge']['assigned']} | "
            f"{r['audit']['stationarity']:.6g} | {r['configured_reference_distance_km']:.3f} | "
            f"{r['common_timing_s']:.3f} | {r['q_change_rms']:.5f} | "
            f"{np.round(r['band_update_hz'], 2).tolist()} |"
        )
    lines += [
        "",
        "Configured distances use the same five metadata-qualified operator-supplied "
        "roof references; survey and altitude uncertainty remain unknown. They enter only after "
        "the global outcome seal. Fit/NLL gains do not imply position gains. The position CDF "
        "keeps all five sources and marks nonstationary selectors with x. No best-of-truth "
        "position, window or RF-arm mixture is formed.",
        "",
        "## All fifteen requested windows",
        "",
        "| Window | Original/N | Fixed fitted c | Joint fitted c | Fixed c0 | Joint c0 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for w in window_ids:
        data = [
            next(
                r for r in windows if r["window"] == w and r["arm"] == arm and r["method"] == method
            )
            for arm in ("fitted-c", "zero-c")
            for method in ("fixed", "joint")
        ]
        lines.append(
            f"| {w} | {data[0]['original_assigned']}/{data[0]['observations']} | "
            + " | ".join(str(r["assigned"]) for r in data)
            + " |"
        )
    lines += [
        "",
        "The≥80% net-original-missing restoration label is descriptive coverage only. "
        "All labels and complete per-window new/lost/retained, row-NLL sums, paired RMS and "
        "unchanged denominators are in evaluation.json; no identity truth is inferred. The "
        "separate recovery_identity_audit demonstrates why point counts and dominant model-ID "
        "support must remain distinct.",
        "",
        "## Method, constraints and cost",
        "",
        "Seeds are the exact iteration2 fixed-profile fitted-c complete states for every source. "
        "Both policies retain the original shared likelihood, original ordered candidates, q, "
        "visibility, timing priors2s/3s, clocks and physical priors/bounds. Both use the broad "
        "regional research disk; extra original-production25km disks are not imposed. Original "
        "production KKT/local-domain flags are not copied into new audits. Each original point "
        "and profile seed was independently replayed under each current target and RF arm.",
        "",
        "Joint offsets are absolute RX-specific high-band constants, bounded±ALIAS/2 with the "
        "same50000Hz prior replacing the frozen constant exactly once. Original physical, clock "
        "and q coordinates remain free. Updates are in the same source frame but remain coupled "
        "with other calibration/timing/geography; they are not hardware offset measurements.",
        "",
        "Each new policy receives1000 objective/density calls and120 active seconds. The joint "
        "policy charges159 finite profile calls plus2 exact runtime qualifiers and≤839 refit "
        "calls. Profiles precomputed from the exact same complete states were requalified before "
        "reuse and their active calls/time charged; no free profile optimization is hidden. "
        "Fixed controls get1000 common.refit calls from the same complete seeds. This is a "
        "profile-plus-joint policy comparison, not a parameter-count-only causal experiment.",
        "",
        "Each family reuses one immutable public preparation with fresh parameter copies and "
        "bank/observation/design fingerprint checks. Family preparation seconds and case wall "
        "times are separately retained in family_seal_Sxx.json. At most two families run under "
        "540s TERM/545s KILL caps; per-case inference limits remain unchanged. Independent "
        "terminal audits, actual qualification and public source preparation are additional to "
        "inference. Post-seal scoring makes45 explicit model-classification calls plus public "
        "original-source replay/preparation. No hidden retry or endpoint polish is applied.",
        "",
        "Version1 schema failure and original source/protocol/logs are retained. It required an "
        "optional mode field missing in every canonical historical seed. Version2 verifies exact "
        "path/source/job/input/terminal/TLE/method/arm authority and independently replays each "
        "fitted seed's full-observation J/NLL. This changes no scientific threshold or data. "
        "The earlier absent-cache preflight was corrected before source freeze with public "
        "reconstruction from the same original pinned local TLE; no provider or candidate changes.",
        "",
        "Thirteen harness/shared-model tests, three family tests and two paired-metric tests pass. "
        "Actual ten source/RF qualifications pass exact nesting/profile J/NLL, original gradient "
        "and posterior closure, both new-band derivatives and unchanged classification; their "
        "source/profile/incumbent receipts are sealed before fits. Full-data development results "
        "do not substitute for blocked predictive evaluation. No production/DS21/DS22 promotion "
        "is authorized by this report alone.",
    ]
    lines += [
        "",
        "## Measured execution costs",
        "",
        "| Source | One preparation seconds | Four-case family seconds | "
        "Fixed charged calls (both RF arms) | Joint charged calls (both RF arms) |",
        "|---|---:|---:|---:|---:|",
    ]
    for source in SOURCES:
        family = read(HERE / f"family_seal_{source}.json")
        fixed_calls = sum(
            r["diagnostics"]["evaluations"]
            for r in rows
            if r["source_id"] == source and r["method"] == "fixed"
        )
        joint_calls = sum(
            r["diagnostics"]["evaluations"]
            for r in rows
            if r["source_id"] == source and r["method"] == "joint"
        )
        lines.append(
            f"| {source} | {family['preparation_seconds']:.3f} | "
            f"{family['elapsed_seconds']:.3f} | {fixed_calls} | {joint_calls} |"
        )
    matrix = read(HERE / "family_matrix.json")
    lines += [
        "",
        f"The two-worker matrix completed in{matrix['elapsed_seconds']:.3f}s. "
        "Charged inference totals7944 objective/density calls, including1590 actual profile "
        "calls computed once during qualification and re-used with their original costs. "
        "Additional declared actual qualification is110 model objectives plus public replay "
        "preparation, followed by20 independent terminal audits. Failed-v1 preparation, ten "
        "successful qualification preparations and five fit-family preparations are separate "
        "from the fitting allowance; post-seal evaluation performs five additional public "
        "preparations and45 explicit classification objectives. Public preparation's internal "
        "source audits are additional and were not instrumented as zero cost.",
    ]
    (HERE / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
