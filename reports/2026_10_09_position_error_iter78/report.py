"""Full148 coverage with explicitly matched partial results until completion."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from report_metrics import distribution, paired

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")


def read(path):
    return json.loads(path.read_text())


def load_result(binding, digest):
    member = binding["member"]
    path = HERE / "results" / f"{member['inventory_label']}.json"
    row = read(path) if path.exists() else dict(status="pending")
    if path.exists():
        assert row["protocol_sha256"] == digest
        assert row["member"] == member
    return row


def main(plan_path=None):
    plan_path = plan_path or HERE / "protocol.json"
    plan = read(plan_path)
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    old = {
        r["member"]["inventory_label"]: r
        for r in read(ROOT / "reports/2026_10_09_position_error_iter65/snapshot.json")["cases"]
    }
    coverage, available = [], {}
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        row = load_result(binding, digest)
        coverage.append(dict(
            member=member, status=row["status"], error=row.get("error"),
            provenance=row.get("provenance"),
        ))
        if row["status"] in ("complete", "upstream_stopped"):
            available[label] = row
    groups = {
        d: [b for b in plan["members"] if b["member"]["dataset"] == d]
        for d in ("DS16", "DS17", "DS18")
    }
    groups["Pooled"] = plan["members"]
    groups["DS16-original48"] = [
        b for b in groups["DS16"] if b["loader_binding"]["kind"] == "legacy_ds16"
    ]
    groups["DS16-added15"] = [
        b for b in groups["DS16"] if b["loader_binding"]["kind"] != "legacy_ds16"
    ]
    groups["DS18-prior24"] = [
        b for b in groups["DS18"] if b["member"]["exposure"] == "previously_evaluated_consumed"
    ]
    groups["DS18-other10-consumed"] = [
        b for b in groups["DS18"] if b["member"]["exposure"] != "previously_evaluated_consumed"
    ]
    controls = []
    for binding in plan["members"]:
        label = binding["member"]["inventory_label"]
        if label not in available or "raw" not in available[label]:
            continue
        previous = read(ROOT / binding["result_source"])["extension"]["stages"]["slope-0.25"]
        for arm in ARMS:
            before = previous[arm]
            after = available[label]["raw"]["0.25"][arm]
            controls.append(
                dict(
                    label=label,
                    arm=arm,
                    objective_delta=after["objective"] - before["objective"],
                    before_converged=before["converged"],
                    after_converged=after["converged"],
                    before_error_km=before["error_km"],
                    after_error_km=after["error_km"],
                    elapsed_s=after["elapsed_s"],
                )
            )
    summary = dict(coverage=coverage, groups={}, historical_raw_control_audit=controls)
    for name, bindings in groups.items():
        labels = [b["member"]["inventory_label"] for b in bindings]
        matched = [label for label in labels if label in available]
        group = dict(membership=len(labels), available=len(matched), arms={})
        for arm in ARMS:
            baseline = [old[x]["arms"][arm]["baseline"]["error_km"] for x in matched]
            control = [available[x]["operational"]["0.25"][arm]["error_km"] for x in matched]
            arms = dict(
                baseline_full=distribution(
                    [old[x]["arms"][arm]["baseline"]["error_km"] for x in labels]
                ),
                baseline_matched=distribution(baseline),
                variants={},
            )
            arms["baseline_frequency_rms_matched_hz"] = distribution(
                [old[x]["arms"][arm]["baseline"]["rms_hz"] for x in matched]
            )
            for sigma in plan["sigmas"]:
                fits = [available[x]["operational"][str(sigma)][arm] for x in matched]
                errors = [r["error_km"] for r in fits]
                raw = [available[x].get("raw", {}).get(str(sigma), {}).get(arm) for x in matched]
                frequency = [
                    r["posterior_rms_hz"] for r in fits if r.get("posterior_rms_hz") is not None
                ]
                arms["variants"][str(sigma)] = dict(
                    position=distribution(errors),
                    versus_baseline=paired(errors, baseline),
                    versus_new_control=paired(errors, control),
                    frequency_rms_hz=distribution(frequency),
                    raw_failed=sum(r is not None and not r["converged"] for r in raw),
                    not_attempted=sum(r is None for r in raw),
                    accepted_converged=sum(bool(r["converged"]) for r in fits),
                    operational_stage_counts=dict(Counter(r["stage"] for r in fits)),
                )
            arms["new_control_vs_historical"] = paired(
                control, [old[x]["arms"][arm]["candidate"]["error_km"] for x in matched]
            )
            group["arms"][arm] = arms
        summary["groups"][name] = group
    summary["complete"] = len(available) == 148
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Iteration78 sensitivity results",
        "",
        f"**{len(available)}/148 members have results; "
        f"{'complete' if summary['complete'] else 'partial, not a full-cohort conclusion'}.**",
        "",
        "All members remain below, including pending/input failures. Numerical failures "
        "retain fixed fallbacks. Comparisons use identical available membership per group; "
        "the JSON also retains the full frozen baseline. All data are consumed development.",
        "",
        "| Dataset | Arm | Sigma Hz/s | Available / all | Mean km | Median km | "
        "p95 km | Worst km | Raw failed / not attempted |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    fig.suptitle(
        f"{'Complete' if summary['complete'] else 'Partial'}: {len(available)}/148 recordings; "
        "matched c arms, consumed development"
    )
    for ax, arm in zip(axes, ARMS, strict=True):
        for name in ("DS16", "DS17", "DS18"):
            g = summary["groups"][name]
            points = []
            for sigma in plan["sigmas"]:
                r = g["arms"][arm]["variants"][str(sigma)]
                m = r["position"]
                cells = [
                    "pending" if m[k] is None else f"{m[k]:.6f}"
                    for k in ("mean", "median", "p95", "worst")
                ]
                lines.append(
                    f"| {name} | {arm} | {sigma} | {g['available']} / "
                    f"{g['membership']} | "
                    + " | ".join(cells)
                    + f" | {r['raw_failed']} / {r['not_attempted']} |"
                )
                if m["mean"] is not None:
                    points.append((sigma, m["mean"]))
            if points:
                points.sort()
                ax.plot(
                    [p[0] for p in points], [p[1] for p in points], "o-",
                    label=f"{name} ({g['available']}/{g['membership']})",
                )
        ax.set(
            title=arm, xlabel="Satellite slope prior sigma, Hz/s", ylabel="Mean position error, km"
        )
        ax.axhline(1, color="gray", linestyle="--")
        if ax.lines and len(ax.lines) > 1:
            ax.legend()
    fig.savefig(HERE / "comparison.png", dpi=170)
    plt.close(fig)
    lines += [
        "",
        "![Matched available-member means](comparison.png)",
        "",
        "Position and frequency statistics are separate in [summary.json](summary.json), "
        "with paired regressions, subgroups, convergence and fallback stages. "
        "No reference-error-based per-scan selection occurs. Changed-model scores are "
        "not ranked against one another. New90s controls may differ from old20s fits.",
        "",
        "| Member | Session | Status | Failure |",
        "|---|---|---|---|",
    ]
    for row in coverage:
        m = row["member"]
        failure = str(row["error"] or "").replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {m['inventory_label']} | {m['session_id']} | {row['status']} | {failure} |"
        )
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(len(available), "of148 available; all148 in coverage")


if __name__ == "__main__":
    main()
