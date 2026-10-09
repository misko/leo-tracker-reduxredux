"""Full-membership paired-data descriptions; no new positioning or selection."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

ARMS = ("fitted-c", "zero-c")
METHODS = ("raw", "unadjusted_shrinkage", "background_projected", "smooth_clock_projected")
DATASETS = ("DS16", "DS17", "DS18")


def distribution(values):
    values = [v for v in values if v is not None]
    assert all(np.isfinite(values)), "Nonfinite diagnostic cannot silently disappear"
    if not values:
        return dict(count=0, mean=None, median=None, p95=None, worst=None)
    return dict(
        count=len(values),
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        p95=float(np.percentile(values, 95)),
        worst=float(np.max(values)),
    )


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values) ** 2))) if len(values) else None


def compact_arm(row):
    """Reduce one raw receipt to per-group/per-recording descriptions."""
    paired = row["paired_rows"]
    assert row["pair_count"] == len(paired)
    values = np.asarray([p["difference_hz"] for p in paired], float)
    satellites = np.asarray([p["satellite"] for p in paired], int)
    assert np.isfinite(values).all()
    primary = row["background_projected"]
    eligible = [int(i) for i in primary["eligible_satellite_ids"]]
    mask = np.isin(satellites, eligible)
    raw = [float(np.mean(values[satellites == i])) for i in eligible]
    methods = dict(
        raw=dict(
            signed_contrasts_hz=raw,
            mean_abs_hz=float(np.mean(np.abs(raw))) if raw else None,
            median_abs_hz=float(np.median(np.abs(raw))) if raw else None,
            data_rank=None,
            rank_fraction=None,
            no_op=len(eligible) < 2,
            regularized_rank=None,
            background_rank=None,
            fit_rms=None,
        )
    )
    for method in METHODS[1:]:
        fitted = row[method]
        assert [int(i) for i in fitted["eligible_satellite_ids"]] == eligible
        lookup = dict(zip(fitted["satellite_ids"], fitted["contrasts_hz"], strict=True))
        contrasts = [float(lookup[i]) for i in eligible]
        assert np.isfinite(contrasts).all()
        rank = fitted.get("data_rank")
        fit_rms = None
        if len(eligible) >= 2:
            y = values[mask]
            delta = np.asarray([lookup[int(i)] for i in satellites[mask]])
            if "residual_hz" in fitted:
                residual = np.asarray(fitted["residual_hz"], float)
                assert residual.shape == y.shape and np.isfinite(residual).all()
                background = y - delta - residual
            else:
                residual, background = y - delta, np.zeros(len(y))
            fit_rms = dict(
                eligible_pairs=len(y),
                raw_rms_hz=rms(y),
                fitted_common_background_rms_hz=rms(background),
                after_background_rms_hz=rms(y - background),
                contrast_rms_hz=rms(delta),
                final_residual_rms_hz=rms(residual),
            )
        methods[method] = dict(
            signed_contrasts_hz=contrasts,
            mean_abs_hz=float(np.mean(np.abs(contrasts))) if contrasts else None,
            median_abs_hz=float(np.median(np.abs(contrasts))) if contrasts else None,
            data_rank=rank,
            rank_fraction=rank / (len(eligible) - 1)
            if rank is not None and len(eligible) >= 2
            else None,
            no_op=bool(fitted["no_op"]),
            no_identified_modes=rank == 0,
            regularized_rank=fitted.get("regularized_rank"),
            background_rank=fitted.get("background_rank"),
            fit_rms=fit_rms,
        )
    return dict(
        pair_count=len(values),
        eligible_pair_count=int(mask.sum()),
        eligible_satellite_ids=eligible,
        eligible_group_count=len(eligible),
        raw_pair_mean_hz=row["raw_pair_mean_hz"],
        raw_pair_rms_hz=row["raw_pair_rms_hz"],
        methods=methods,
    )


def aggregate(cases, arm):
    available = [case["arms"][arm] for case in cases if case["status"] == "complete"]
    methods = {}
    for method in METHODS:
        rows = [r["methods"][method] for r in available]
        fits = [r["fit_rms"] for r in rows if r["fit_rms"] is not None]
        methods[method] = dict(
            signed_group_contrasts_hz=distribution(
                [v for r in rows for v in r["signed_contrasts_hz"]]
            ),
            per_recording_mean_abs_hz=distribution([r["mean_abs_hz"] for r in rows]),
            per_recording_median_abs_hz=distribution([r["median_abs_hz"] for r in rows]),
            no_op_count=sum(r["no_op"] for r in rows),
            no_identified_modes_count=sum(r.get("no_identified_modes", False) for r in rows),
            data_rank=distribution([r["data_rank"] for r in rows]),
            rank_fraction=distribution([r["rank_fraction"] for r in rows]),
            regularized_rank=distribution([r["regularized_rank"] for r in rows]),
            background_rank=distribution([r["background_rank"] for r in rows]),
            pair_fit_rms={
                key: distribution([f[key] for f in fits])
                for key in (
                    "raw_rms_hz",
                    "fitted_common_background_rms_hz",
                    "after_background_rms_hz",
                    "contrast_rms_hz",
                    "final_residual_rms_hz",
                )
            },
        )
    return dict(
        available_recordings=len(available),
        total_pairs=sum(r["pair_count"] for r in available),
        eligible_pairs=sum(r["eligible_pair_count"] for r in available),
        eligible_recording_satellite_groups=sum(r["eligible_group_count"] for r in available),
        raw_pair_mean_hz=distribution([r["raw_pair_mean_hz"] for r in available]),
        raw_pair_rms_hz=distribution([r["raw_pair_rms_hz"] for r in available]),
        methods=methods,
    )


def summarize(plan, receipts, digest):
    bindings = plan["members"]
    labels = [b["member"]["inventory_label"] for b in bindings]
    assert len(labels) == len(set(labels)) == 148
    assert not (set(receipts) - set(labels))
    assert plan["contrast_sigma_hz"] == 30 and plan["pair_variance_hz2"] == 31250
    cases = []
    for binding in bindings:
        member = binding["member"]
        receipt = receipts.get(member["inventory_label"])
        case = dict(
            member=member,
            loader_kind=binding["loader_binding"]["kind"],
            status="missing",
            error=None,
            arms=None,
            objective_checks=None,
        )
        if receipt:
            assert receipt["member"] == member and receipt["protocol_sha256"] == digest
            assert receipt["status"] in ("complete", "failed")
            case.update(
                status=receipt["status"],
                error=receipt.get("error"),
                objective_checks=receipt.get("objective_checks"),
            )
            if receipt["status"] == "complete":
                assert receipt["sigma_hz"] == 30 and receipt["pair_variance_hz2"] == 31250
                for arm in ARMS:
                    assert abs(receipt["objective_checks"][arm]["delta"]) <= 1e-6
                keys = ("satellite", "channel", "tick_ms", "rx0_indices", "rx1_indices")
                assert [
                    tuple(p[k] if not isinstance(p[k], list) else tuple(p[k]) for k in keys)
                    for p in receipt["arms"][ARMS[0]]["paired_rows"]
                ] == [
                    tuple(p[k] if not isinstance(p[k], list) else tuple(p[k]) for k in keys)
                    for p in receipt["arms"][ARMS[1]]["paired_rows"]
                ]
                case["arms"] = {arm: compact_arm(receipt["arms"][arm]) for arm in ARMS}
        cases.append(case)
    subsets = {d: [c for c in cases if c["member"]["dataset"] == d] for d in DATASETS}
    assert {d: len(rows) for d, rows in subsets.items()} == dict(DS16=63, DS17=51, DS18=34)
    subsets.update(Pooled=cases)
    subsets["DS16-original48"] = [c for c in subsets["DS16"] if c["loader_kind"] == "legacy_ds16"]
    subsets["DS16-added15"] = [c for c in subsets["DS16"] if c["loader_kind"] != "legacy_ds16"]
    subsets["DS18-prior24"] = [
        c for c in subsets["DS18"] if c["member"].get("exposure") == "previously_evaluated_consumed"
    ]
    subsets["DS18-other10-consumed"] = [
        c for c in subsets["DS18"] if c["member"].get("exposure") != "previously_evaluated_consumed"
    ]
    groups = {
        name: dict(
            membership=len(rows),
            statuses=dict(Counter(c["status"] for c in rows)),
            arms={arm: aggregate(rows, arm) for arm in ARMS},
        )
        for name, rows in subsets.items()
    }
    return dict(
        complete=all(c["status"] == "complete" for c in cases),
        membership=148,
        statuses=dict(Counter(c["status"] for c in cases)),
        cases=cases,
        groups=groups,
        contrast_sigma_hz=30,
        pair_variance_hz2=31250,
        scope="Consumed descriptive diagnostics; no position fit/accuracy effect. "
        "Available-recording aggregates explicitly retain missing/failed coverage. "
        "Recording/satellite samples are correlated; RMS is not calibrated variance.",
    )


def render(summary, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for dataset in DATASETS:
            rows = [
                c["arms"][arm]["methods"]
                for c in summary["cases"]
                if c["status"] == "complete" and c["member"]["dataset"] == dataset
            ]
            points = [
                (
                    r["background_projected"]["mean_abs_hz"],
                    r["smooth_clock_projected"]["mean_abs_hz"],
                )
                for r in rows
                if r["background_projected"]["mean_abs_hz"] is not None
            ]
            if points:
                ax.scatter(*zip(*points, strict=True), label=dataset, alpha=0.7)
        bound = max(*ax.get_xlim(), *ax.get_ylim(), 1)
        ax.plot([0, bound], [0, bound], color="gray", linestyle="--", linewidth=1)
        ax.set(
            xlabel="Linear/channel projected mean |contrast| (Hz)",
            ylabel="Existing smooth-clock projected mean |contrast| (Hz)",
            title=arm,
        )
        if ax.collections:
            ax.legend()
    fig.suptitle("Descriptive receiver contrasts; no position-accuracy claim")
    fig.savefig(output / "contrast-comparison.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for column, arm in enumerate(ARMS):
        rows = [c["arms"][arm]["methods"] for c in summary["cases"] if c["status"] == "complete"]
        all_values = [
            v for r in rows for method in METHODS for v in r[method]["signed_contrasts_hz"]
        ]
        common_bins = np.histogram_bin_edges(all_values, bins=35) if all_values else 35
        for method in METHODS:
            values = [v for r in rows for v in r[method]["signed_contrasts_hz"]]
            if values:
                axes[0, column].hist(values, bins=common_bins, histtype="step", label=method)
        for method in METHODS[2:]:
            values = [
                r[method]["rank_fraction"] for r in rows if r[method]["rank_fraction"] is not None
            ]
            if values:
                axes[1, column].hist(
                    values, bins=np.linspace(0, 1, 11), histtype="step", label=method
                )
        axes[0, column].set(
            title=arm, xlabel="Signed group contrast (Hz)", ylabel="Correlated groups"
        )
        axes[1, column].set(
            xlabel="Identified data rank / possible contrast dimensions", ylabel="Recordings"
        )
        for row in range(2):
            if axes[row, column].lines or axes[row, column].patches:
                axes[row, column].legend(fontsize=8)
    fig.savefig(output / "contrast-distributions.png", dpi=170)
    plt.close(fig)
    lines = [
        "# Iteration90: paired receiver differences and clock confounding",
        "",
        f"Coverage: **{summary['membership']} members**, statuses `{summary['statuses']}`. "
        "Every missing/input/reconstruction failure remains in coverage; numerical tables "
        "describe explicitly available recordings only.",
        "",
        "Fixed30Hz contrast prior; fixed pair precision1/31250Hz². Both c arms use "
        "the same fitted-derived assignment and exact paired membership. The smooth sensitivity "
        "adds only the existing B7 smooth-clock span. No new position, accuracy improvement, "
        "physical hardware diagnosis or independent validation is claimed.",
        "",
        "![Per-recording contrast comparison](contrast-comparison.png)",
        "",
        "![Contrasts and identified data-rank fractions](contrast-distributions.png)",
        "",
        "| Dataset | Arm | Available/member | Pairs | Eligible groups | "
        "Raw mean | Unadjusted | Linear | Smooth |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def number(value):
        return "—" if value is None else f"{value:.3f}"

    for dataset, group in summary["groups"].items():
        for arm in ARMS:
            row = group["arms"][arm]
            values = [
                number(row["methods"][m]["per_recording_mean_abs_hz"]["median"]) for m in METHODS
            ]
            lines.append(
                f"| {dataset} | {arm} | {row['available_recordings']}/{group['membership']} | "
                f"{row['total_pairs']} | {row['eligible_recording_satellite_groups']} | "
                + " | ".join(values)
                + " |"
            )
    lines += [
        "",
        "Entries are median per-recording mean absolute eligible-group contrast, Hz. "
        "Raw means contain common effects; unadjusted shrinkage is not background-adjusted.",
        "",
        "| Dataset | Arm | Background | No-op | No identified modes | Median rank fraction | "
        "Median background RMS Hz | Median after-background RMS Hz | Median final RMS Hz |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset in (*DATASETS, "Pooled"):
        for arm in ARMS:
            for method in METHODS[2:]:
                row = summary["groups"][dataset]["arms"][arm]["methods"][method]
                fit = row["pair_fit_rms"]
                lines.append(
                    f"| {dataset} | {arm} | {method} | {row['no_op_count']} | "
                    f"{row['no_identified_modes_count']} | "
                    f"{number(row['rank_fraction']['median'])} | "
                    f"{number(fit['fitted_common_background_rms_hz']['median'])} | "
                    f"{number(fit['after_background_rms_hz']['median'])} | "
                    f"{number(fit['final_residual_rms_hz']['median'])} |"
                )
    lines += [
        "",
        "Background RMS describes the fitted common clock/channel prediction; after-background "
        "RMS retains the fitted contrast plus residual. These are descriptive projections, not "
        "an additive variance decomposition or proof of physical identifiability. Data rank, "
        "regularized rank and no-ops are distinct. No calibrated uncertainty or position effect.",
        "",
        "[Compact summaries and complete membership](summary.json); "
        "raw receipts remain under results/.",
        "",
        "| Member | Status | Failure |",
        "|---|---|---|",
    ]
    for case in summary["cases"]:
        error = str(case["error"] or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {case['member']['inventory_label']} | {case['status']} | {error} |")
    (output / "RESULTS.md").write_text("\n".join(lines) + "\n")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")


def main():
    here = Path(__file__).resolve().parent
    path = here / "protocol.json"
    plan = json.loads(path.read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    receipts = {p.stem: json.loads(p.read_text()) for p in (here / "results").glob("*.json")}
    render(summarize(plan, receipts, digest), here)


if __name__ == "__main__":
    main()
