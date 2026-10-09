"""Complete-membership reporting for the fixed geometry-prior experiment."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "2026_10_09_position_error_iter78"))
from report_metrics import distribution, paired  # noqa: E402

ARMS = ("fitted-c", "zero-c")
VARIANTS = ("uniform0.5", "protected0.25")


def read(path):
    return json.loads(path.read_text())


def variant_metrics(rows, variant, arm):
    if any(r["status"] != "complete" for r in rows):
        return None
    fits = [r["result"]["operational"][variant][arm] for r in rows]
    raw = [r["result"]["raw"][variant][arm] for r in rows]
    values = [f["error_km"] for f in fits]
    control = [r["result"]["operational"]["uniform0.5"][arm]["error_km"] for r in rows]
    archived = [r["archived"][arm]["error_km"] for r in rows]
    baseline = [r["baseline"][arm]["error_km"] for r in rows]
    return dict(
        position=distribution(values), frequency_rms_hz=distribution(
            [f["posterior_rms_hz"] for f in fits]),
        versus_new_control=paired(values, control),
        versus_archived_control=paired(values, archived),
        versus_baseline=paired(values, baseline), raw_failed=sum(not f["converged"] for f in raw),
        accepted_converged=sum(f["converged"] for f in fits),
        operational_stages=dict(Counter(f["stage"] for f in fits)),
    )


def main():
    plan = read(HERE / "protocol.json")
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    baseline = {r["member"]["inventory_label"]: r["arms"] for r in read(
        HERE.parent / "2026_10_09_position_error_iter65/snapshot.json")["cases"]}
    cases, audit = [], []
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        path = HERE / "results" / f"{label}.json"
        result = read(path) if path.exists() else dict(status="pending")
        if path.exists():
            assert result["member"] == member and result["protocol_sha256"] == digest
        old = read(ROOT / binding["control_source"])
        cases.append(dict(
            member=member, loader_kind=binding["loader_binding"]["kind"], status=result["status"],
            error=result.get("error"), result=result, archived=old["operational"]["0.5"],
            baseline={a: baseline[label][a]["baseline"] for a in ARMS},
        ))
        if result["status"] == "complete":
            for arm in ARMS:
                before, after = old["raw"]["0.5"][arm], result["raw"]["uniform0.5"][arm]
                audit.append(dict(label=label, arm=arm,
                                  objective_delta=after["objective"] - before["objective"],
                                  before_converged=before["converged"],
                                  after_converged=after["converged"],
                                  elapsed_s=after["elapsed_s"]))
    groups = {d: [r for r in cases if r["member"]["dataset"] == d]
              for d in ("DS16", "DS17", "DS18")}
    groups["Pooled"] = cases
    groups["DS16-original48"] = [r for r in groups["DS16"] if r["loader_kind"] == "legacy_ds16"]
    groups["DS16-added15"] = [r for r in groups["DS16"] if r["loader_kind"] != "legacy_ds16"]
    groups["DS18-prior24"] = [r for r in groups["DS18"]
                            if r["member"]["exposure"] == "previously_evaluated_consumed"]
    groups["DS18-other10-consumed"] = [r for r in groups["DS18"]
                                    if r["member"]["exposure"] != "previously_evaluated_consumed"]
    summary = dict(cases=cases, groups={}, raw_control_audit=audit,
                   complete=all(r["status"] == "complete" for r in cases))
    for name, rows in groups.items():
        summary["groups"][name] = dict(
            membership=len(rows), complete=sum(r["status"] == "complete" for r in rows),
            input_statuses=dict(Counter(r["status"] for r in rows)),
            geometry_ranks=dict(Counter(r["result"]["geometry"]["rank"] for r in rows
                                       if r["status"] == "complete")),
            arms={a: dict(
                baseline=distribution([r["baseline"][a]["error_km"] for r in rows]),
                archived_control=distribution([r["archived"][a]["error_km"] for r in rows]),
                variants={v: variant_metrics(rows, v, a) for v in VARIANTS},
            ) for a in ARMS},
        )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# Iteration84 geometry-prior comparison", "",
             f"**{summary['groups']['Pooled']['complete']}/148 complete. "
             f"{'Full comparison.' if summary['complete'] else 'Full candidate means withheld.'}**",
             "", "All original48/added15 DS16,51 DS17 and34 DS18 members remain included. "
             "DS18 prior24/other10 exposure labels are preserved; all are consumed development. "
             "The geometry rule uses shared hypothesis positions, never reference positions. "
             "An input failure remains unavailable, not zero error. Numerical failures retain "
             "the fixed archived0.5 fallback and are reported separately.", "",
             "| Dataset | Arm | Variant | Mean km | Median km | p95 km | Worst km | "
             "Improved/regressed/tied vs new control | Raw failed | RMS Hz |",
             "|---|---|---|---:|---:|---:|---:|---|---:|---:|"]
    for name in ("DS16", "DS17", "DS18", "Pooled"):
        for arm in ARMS:
            for variant in VARIANTS:
                values = summary["groups"][name]["arms"][arm]["variants"][variant]
                if values is None:
                    lines.append(f"| {name} | {arm} | {variant} | "
                                 "pending | — | — | — | — | — | — |")
                    continue
                position, comparison = values["position"], values["versus_new_control"]
                lines.append(f"| {name} | {arm} | {variant} | " + " | ".join(
                    f"{position[k]:.6f}" for k in ("mean", "median", "p95", "worst"))
                    + f" | {comparison['improved']}/{comparison['regressed']}/{comparison['tied']}"
                    + f" | {values['raw_failed']} | {values['frequency_rms_hz']['mean']:.3f} |")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    datasets = ("DS16", "DS17", "DS18")
    for ax, arm in zip(axes, ARMS, strict=True):
        if summary["complete"]:
            for variant in VARIANTS:
                ax.plot(datasets, [summary["groups"][d]["arms"][arm]["variants"][variant]
                                   ["position"]["mean"] for d in datasets], "o-", label=variant)
            ax.axhline(1, color="gray", linestyle="--")
            ax.set_ylabel("Mean position error, km")
            ax.legend()
        else:
            ax.bar(datasets, [summary["groups"][d]["complete"] for d in datasets])
            ax.set_ylabel("Completed recordings (not error)")
        ax.set_title(arm)
    fig.suptitle("Fixed geometry prior: " + ("complete148" if summary["complete"] else "PENDING"))
    fig.savefig(HERE / "comparison.png", dpi=170)
    plt.close(fig)
    lines += ["", "![Comparison or completion progress](comparison.png)", "",
              "[summary.json](summary.json) includes baseline/archived-control distributions, "
              "all paired regressions, subgroup metrics, raw control reproduction and projector "
              "ranks. Frequency RMS is separate from position accuracy. c0 also locks RF-time "
              "terms; matched arms share fitted-derived seeds, banks and the fixed projector. "
              "No inference from a better in-sample fit alone, and no deployment claim.", "",
              "| Member | Session | Status | Failure |", "|---|---|---|---|"]
    for row in cases:
        m = row["member"]
        error = str(row["error"] or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {m['inventory_label']} | {m['session_id']} | {row['status']} | {error} |")
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(summary["groups"]["Pooled"]["complete"], "of148 complete")


if __name__ == "__main__":
    main()
