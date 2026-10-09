"""Report complete-membership ablations, never omit failed or pending inputs."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")
MAIN = ("B0", "B1", "B2", "B3", "B4", "B4W", "B5", "B6", "B7")
PAIRS = (
    ("B1", "B0"),
    ("B2", "B0"),
    ("B3", "B1"),
    ("B3", "B2"),
    ("B4", "C3"),
    ("B4W", "C4"),
    ("B5", "C5"),
    ("B6", "C6"),
    ("B7", "C6"),
    ("B7", "B6"),
    ("B7", "B0"),
)


def distribution(values):
    x = np.asarray(values, float)
    if not len(x):
        return None
    assert np.isfinite(x).all()
    return dict(
        n=len(x),
        mean=float(x.mean()),
        median=float(np.median(x)),
        p95=float(np.percentile(x, 95)),
        worst=float(x.max()),
    )


def paired(after, before):
    delta = np.asarray(after) - np.asarray(before)
    return dict(
        n=len(delta),
        mean_delta_km=float(delta.mean()),
        improved=int(sum(delta < -1e-6)),
        regressed=int(sum(delta > 1e-6)),
        tied=int(sum(abs(delta) <= 1e-6)),
        worst_regression_km=float(delta.max()),
        regressed_over_100m=int(sum(delta > 0.1)),
        improved_over_100m=int(sum(delta < -0.1)),
    )


def stage_metrics(rows, stage, arm):
    if any(r["status"] != "complete" for r in rows):
        return None
    chosen = [r["stages"][stage][arm] for r in rows]
    raw = [r.get("raw", {}).get(stage, {}).get(arm) for r in rows]
    errors = [r["error_km"] for r in chosen]
    return dict(
        position=distribution(errors),
        frequency_rms_hz=distribution([r["posterior_rms_hz"] for r in chosen]),
        thresholds={str(k): sum(e > k for e in errors) for k in (1, 5, 10, 100)},
        raw_failed=sum(r is not None and not r["converged"] for r in raw),
        not_attempted=0 if stage in ("B0", "B1") else sum(r is None for r in raw),
        fallbacks=sum(r["stage"] != stage for r in chosen),
        selected_stages=dict(Counter(r["stage"] for r in chosen)),
        fit_seconds=distribution([r["elapsed_s"] for r in raw if r and "elapsed_s" in r]),
        versus_baseline=paired(errors, [r["stages"]["B0"][arm]["error_km"] for r in rows]),
    )


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    snapshot = json.loads(
        (HERE.parent / "2026_10_09_position_error_iter65/snapshot.json").read_text()
    )
    baseline = {r["member"]["inventory_label"]: r["arms"] for r in snapshot["cases"]}
    rows = []
    for b in plan["members"]:
        label = b["member"]["inventory_label"]
        path = HERE / "results" / f"{label}.json"
        row = (
            json.loads(path.read_text())
            if path.exists()
            else dict(status="pending", member=b["member"])
        )
        if path.exists():
            assert row["protocol_sha256"] == digest and row["member"] == b["member"]
            if row["status"] == "complete":
                for arm in ARMS:
                    np.testing.assert_allclose(
                        row["stages"]["B0"][arm]["error_km"],
                        baseline[label][arm]["baseline"]["error_km"],
                        atol=1e-9,
                        rtol=0,
                    )
        row["loader_kind"] = b["loader_binding"]["kind"]
        rows.append(row)
    groups = {d: [r for r in rows if r["member"]["dataset"] == d] for d in ("DS16", "DS17", "DS18")}
    groups["Pooled"] = rows
    groups["DS16-original48"] = [r for r in groups["DS16"] if r["loader_kind"] == "legacy_ds16"]
    groups["DS16-added15"] = [r for r in groups["DS16"] if r["loader_kind"] != "legacy_ds16"]
    groups["DS18-prior24"] = [
        r for r in groups["DS18"] if r["member"]["exposure"] == "previously_evaluated_consumed"
    ]
    groups["DS18-other10-consumed"] = [
        r for r in groups["DS18"] if r["member"]["exposure"] != "previously_evaluated_consumed"
    ]
    summary = dict(
        complete=all(r["status"] == "complete" for r in rows),
        groups={},
        coverage=[],
        protocol_sha256=digest,
        paired_regressions=[],
    )
    for r in rows:
        summary["coverage"].append(
            dict(
                member=r["member"],
                status=r["status"],
                error=r.get("error"),
                reasons=r.get("reasons"),
            )
        )
    for name, members in groups.items():
        done = all(r["status"] == "complete" for r in members)
        entry = dict(
            membership=len(members),
            complete=sum(r["status"] == "complete" for r in members),
            statuses=dict(Counter(r["status"] for r in members)),
            arms={},
            comparisons={},
        )
        for arm in ARMS:
            entry["arms"][arm] = {s: stage_metrics(members, s, arm) for s in plan["stages"]}
            entry["comparisons"][arm] = {}
            if done:
                for after, before in PAIRS:
                    a = [r["stages"][after][arm]["error_km"] for r in members]
                    b = [r["stages"][before][arm]["error_km"] for r in members]
                    entry["comparisons"][arm][f"{after}-{before}"] = paired(a, b)
        entry["load_seconds"] = distribution(
            [r["load_seconds"] for r in members if r["status"] == "complete"]
        )
        entry["downstream_wall_seconds"] = distribution(
            [r["elapsed_s"] for r in members if r["status"] == "complete"]
        )
        summary["groups"][name] = entry
    for row in rows:
        if row["status"] != "complete":
            continue
        for arm in ARMS:
            for after, before in PAIRS:
                a, b = row["stages"][after][arm], row["stages"][before][arm]
                summary["paired_regressions"].append(
                    dict(
                        label=row["member"]["inventory_label"],
                        arm=arm,
                        comparison=f"{after}-{before}",
                        before_km=b["error_km"],
                        after_km=a["error_km"],
                        delta_km=a["error_km"] - b["error_km"],
                        actual_before_stage=b["stage"],
                        actual_after_stage=a["stage"],
                    )
                )
    summary["rf_locked_control_audit"] = []
    for row in rows:
        if row["status"] != "complete":
            continue
        for stage, arms in row["raw"].items():
            for arm, fit in arms.items():
                if "vector" not in fit:
                    continue
                if arm == "zero-c":
                    assert fit["vector"][6] == 0
                if arm == "zero-c" or stage == "C5":
                    assert all(x == 0 for x in fit.get("rf_drift_coefficients", []))
        a = row["raw"].get("C5", {}).get("zero-c", {})
        b = row["raw"].get("B5", {}).get("zero-c", {})
        if "objective" in a and "objective" in b:
            summary["rf_locked_control_audit"].append(
                dict(
                    label=row["member"]["inventory_label"],
                    objective_delta=b["objective"] - a["objective"],
                    convergence_agrees=a["converged"] == b["converged"],
                )
            )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    total = summary["groups"]["Pooled"]["complete"]
    lines = [
        "# Hard60 ablation: complete membership and position errors",
        "",
        f"**{total}/148 complete.** "
        + (
            "Full comparison." if summary["complete"] else "Full-cohort conclusions remain pending."
        ),
        "",
        "B0 is the saved deployed bounded-recovery hard60 baseline. B0/B1 reuse immutable "
        "search receipts; all downstream fits are fresh with matched90s/600iteration limits. "
        "[Configuration definitions](README.md). All data are consumed development; "
        "reference positions are evaluation-only. Production is unchanged.",
        "",
        "| Dataset | Arm | Stage | Mean km | Median km | p95 km | Worst km | "
        "Raw failures / not attempted / fallback | RMS Hz |",
        "|---|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for name in ("DS16", "DS17", "DS18", "Pooled"):
        for arm in ARMS:
            for stage in plan["stages"]:
                v = summary["groups"][name]["arms"][arm][stage]
                if v is None:
                    lines.append(f"| {name} | {arm} | {stage} | pending | — | — | — | — | — |")
                else:
                    lines.append(
                        f"| {name} | {arm} | {stage} | "
                        + " | ".join(
                            f"{v['position'][k]:.6f}" for k in ("mean", "median", "p95", "worst")
                        )
                        + f" | {v['raw_failed']}/{v['not_attempted']}/{v['fallbacks']} | "
                        f"{v['frequency_rms_hz']['mean']:.3f} |"
                    )
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    for i, arm in enumerate(ARMS):
        for j, dataset in enumerate(("DS16", "DS17", "DS18")):
            ax, g = axes[i, j], summary["groups"][dataset]
            if g["complete"] == g["membership"]:
                means = [g["arms"][arm][s]["position"]["mean"] for s in MAIN]
                ax.bar(MAIN, means)
                ax.axhline(1, color="black", linestyle="--", linewidth=1)
                ax.tick_params(axis="x", rotation=45)
                ax.set_ylabel("Mean position error (km)")
            else:
                ax.text(0.5, 0.5, f"Pending: {g['complete']}/{g['membership']}", ha="center")
            ax.set_title(f"{dataset} / {arm}")
    fig.suptitle("Hard60 ablation — complete dataset means only")
    fig.savefig(HERE / "means.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    for i, arm in enumerate(ARMS):
        for j, dataset in enumerate(("DS16", "DS17", "DS18")):
            ax, members = axes[i, j], groups[dataset]
            if all(r["status"] == "complete" for r in members):
                for stage in ("B0", "B1", "B2", "B3", "B5", "B7"):
                    errors = np.sort([r["stages"][stage][arm]["error_km"] for r in members])
                    ax.step(
                        np.maximum(errors, 1e-4),
                        np.arange(1, len(errors) + 1) / len(errors),
                        where="post",
                        label=stage,
                    )
                ax.set_xscale("log")
                ax.axvline(1, color="black", linestyle="--", linewidth=1)
                ax.legend(fontsize=8)
                ax.set(
                    xlabel="Position error, km (log scale; floor0.0001)", ylabel="Fraction ≤ error"
                )
            else:
                ax.text(0.5, 0.5, "Dataset incomplete", ha="center")
            ax.set_title(f"{dataset} / {arm}")
    fig.suptitle("All-member error distributions; failures retain operational fallbacks")
    fig.savefig(HERE / "distributions.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(15, 16), layout="constrained")
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#dddddd")
    for i, arm in enumerate(ARMS):
        for j, dataset in enumerate(("DS16", "DS17", "DS18")):
            ax, members = axes[i, j], groups[dataset]
            values = np.full((len(members), len(MAIN)), np.nan)
            for k, row in enumerate(members):
                if row["status"] == "complete":
                    values[k] = [max(row["stages"][s][arm]["error_km"], 0.001) for s in MAIN]
            im = ax.imshow(
                values,
                aspect="auto",
                interpolation="nearest",
                cmap=cmap,
                norm=LogNorm(vmin=0.001, vmax=500),
            )
            ax.set_xticks(range(len(MAIN)), MAIN, rotation=45)
            ax.set_yticks(
                range(len(members)),
                [r["member"]["inventory_label"].split("-")[-1] for r in members],
                fontsize=6,
            )
            ax.set_title(f"{dataset} / {arm}")
            ax.set_ylabel("Frozen member index")
    fig.colorbar(
        im,
        ax=axes,
        label="Position error (km), logarithmic; gray = pending/input failure",
        shrink=0.75,
    )
    fig.suptitle(f"Per-scan ablation: {total}/148 complete; all members retained")
    fig.savefig(HERE / "per-scan.png", dpi=160)
    plt.close(fig)
    lines += [
        "",
        "![Mean position errors](means.png)",
        "",
        "![Position error distributions](distributions.png)",
        "",
        "![Per-scan position errors; gray cells are unavailable](per-scan.png)",
        "",
        "summary.json includes every paired regression, thresholds1/5/10/100km, "
        "original48/added15 and prior24/other10 groups, fit times, load times, fallbacks "
        "and frequency residuals separately. Wall times exclude archived search compute; "
        "these are not cold end-to-end pipeline latency measurements. Static c and "
        "RF-time effects are separated by C5/B5; c0 locks RF-time terms.",
        "",
        "| Member | Session | Status | Input failure |",
        "|---|---|---|---|",
    ]
    for r in rows:
        error = str(r.get("error", "")).replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {r['member']['inventory_label']} | {r['member']['session_id']} | "
            f"{r['status']} | {error} |"
        )
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(total, "of148 complete")


if __name__ == "__main__":
    main()
