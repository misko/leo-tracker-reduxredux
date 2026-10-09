"""Report all148 fixed members, failures and matched full-cohort comparisons."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from report_support import effective_result, full_values

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "2026_10_09_position_error_iter78"))
from report_metrics import distribution, paired  # noqa: E402

ARMS = ("fitted-c", "zero-c")


def read(path):
    return json.loads(path.read_text())


def main():
    plan = read(HERE / "protocol.json")
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    old = {r["member"]["inventory_label"]: r for r in read(
        HERE.parent / "2026_10_09_position_error_iter65/snapshot.json"
    )["cases"]}
    cases = []
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        previous = read(ROOT / binding["result_source"])["extension"]["operational"]
        path = HERE / "results" / f"{label}.json"
        row = effective_result(binding, previous, read(path) if path.exists() else None, digest)
        regions = [read(p) for p in sorted((HERE / "regions" / label).glob("*.json"))]
        attempts = [read(p) for p in sorted((HERE / "attempts" / label).glob("*.json"))]
        assert all(r["protocol_sha256"] == digest for r in regions + attempts)
        cases.append(dict(
            member=member, requested=binding["requested_extra_search"],
            loader_kind=binding["loader_binding"]["kind"], status=row["status"],
            error=row.get("error"), operational=row["operational"], control=previous,
            baseline={a: old[label]["arms"][a]["baseline"] for a in ARMS},
            fallback_arms=row.get("fallback_arms", []),
            regional_status_counts=dict(Counter(r["status"] for r in regions)),
            regional_failures=[dict(region=r["region"], error=r.get("error"))
                               for r in regions if r["status"] != "complete"],
            extra_region_seconds=sum(r["elapsed_s"] for r in regions),
            raw_attempts={a: len([r for r in attempts if r["arm"] == a]) for a in ARMS},
            raw_failed={a: sum(not r["fit"]["converged"] for r in attempts if r["arm"] == a)
                        for a in ARMS},
            extra_fit_seconds=sum(r["fit"]["elapsed_s"] for r in attempts),
        ))
    groups = {name: [r for r in cases if r["member"]["dataset"] == name]
              for name in ("DS16", "DS17", "DS18")}
    groups["Pooled"] = cases
    groups["DS16-original48"] = [r for r in groups["DS16"] if r["loader_kind"] == "legacy_ds16"]
    groups["DS16-added15"] = [r for r in groups["DS16"] if r["loader_kind"] != "legacy_ds16"]
    groups["DS18-prior24"] = [r for r in groups["DS18"]
                            if r["member"]["exposure"] == "previously_evaluated_consumed"]
    groups["DS18-other10-consumed"] = [r for r in groups["DS18"]
                                    if r["member"]["exposure"] != "previously_evaluated_consumed"]
    summary = dict(complete=all(r["operational"] is not None for r in cases),
                   groups={}, cases=cases)
    for name, rows in groups.items():
        group = dict(membership=len(rows), requested=sum(r["requested"] for r in rows),
                     available=sum(r["operational"] is not None for r in rows), arms={})
        for arm in ARMS:
            baseline = [r["baseline"][arm]["error_km"] for r in rows]
            control = [r["control"][arm]["error_km"] for r in rows]
            values = full_values(rows, arm, "error_km")
            group["arms"][arm] = dict(
                baseline=distribution(baseline), control=distribution(control),
                candidate=None if values is None else distribution(values),
                versus_baseline=None if values is None else paired(values, baseline),
                versus_control=None if values is None else paired(values, control),
                baseline_frequency_rms_hz=distribution(
                    [r["baseline"][arm]["rms_hz"] for r in rows]),
                control_frequency_rms_hz=distribution(
                    [r["control"][arm]["posterior_rms_hz"] for r in rows]),
                candidate_frequency_rms_hz=None if values is None else distribution(
                    full_values(rows, arm, "posterior_rms_hz")),
                raw_attempts=sum(r["raw_attempts"][arm] for r in rows),
                raw_failed=sum(r["raw_failed"][arm] for r in rows),
                recovery_fallbacks=sum(arm in r["fallback_arms"] for r in rows),
                accepted_converged=None if values is None else sum(
                    r["operational"][arm]["converged"] for r in rows),
                operational_stages=None if values is None else dict(Counter(
                    r["operational"][arm]["stage"] for r in rows)),
            )
        summary["groups"][name] = group
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# Iteration83 full-membership regional recovery", "",
             f"**{'Complete' if summary['complete'] else 'In progress'}: "
             f"{summary['groups']['Pooled']['available']}/148 endpoints determined.**", "",
             "The142 unflagged members retain their frozen control by rule, even before a "
             "worker writes that trivial receipt. Pending recovery members remain in coverage; "
             "no full-group candidate mean is reported until every endpoint is determined.", "",
             "| Dataset | Arm | Endpoint | n | Mean km | Median km | p95 km | Worst km |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for name in ("DS16", "DS17", "DS18", "Pooled"):
        for arm in ARMS:
            stats = summary["groups"][name]["arms"][arm]
            for endpoint in ("baseline", "control", "candidate"):
                values = stats[endpoint]
                if values is None:
                    lines.append(f"| {name} | {arm} | {endpoint} | pending | — | — | — | — |")
                else:
                    lines.append(f"| {name} | {arm} | {endpoint} | {values['n']} | " +
                                 " | ".join(f"{values[k]:.6f}" for k in
                                            ("mean", "median", "p95", "worst")) + " |")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    datasets = ("DS16", "DS17", "DS18")
    for ax, arm in zip(axes, ARMS, strict=True):
        if summary["complete"]:
            for endpoint in ("baseline", "control", "candidate"):
                ax.plot(datasets, [summary["groups"][d]["arms"][arm][endpoint]["mean"]
                                   for d in datasets], "o-", label=endpoint)
            ax.set_ylabel("Mean position error, km")
            ax.axhline(1, color="gray", linestyle="--")
            ax.legend()
        else:
            ax.bar(datasets, [summary["groups"][d]["available"] for d in datasets])
            ax.set_ylabel("Endpoints determined (not error)")
        ax.set_title(arm)
    fig.suptitle("Full148 recovery: " + ("complete" if summary["complete"] else "IN PROGRESS"))
    fig.savefig(HERE / "comparison.png", dpi=170)
    plt.close(fig)
    lines += ["", "![Full-membership comparison or progress](comparison.png)", "",
              "Full paired regressions, convergence/fallbacks, separate frequency statistics, "
              "DS16 original48/added15 and DS18 exposure subgroups are in "
              "[summary.json](summary.json). "
              "The0.5 slope experiment is separate; this control is iteration65 with slope0.25. "
              "All recordings are consumed research; "
              "no independent validation or production change.", "",
              "| Dataset | Arm | Improved/regressed/tied vs control | "
              "Raw failed/attempted | Recovery fallbacks | Control/candidate RMS Hz |",
              "|---|---|---|---:|---:|---|"]
    for name in ("DS16", "DS17", "DS18", "Pooled"):
        for arm in ARMS:
            stats = summary["groups"][name]["arms"][arm]
            change = stats["versus_control"]
            changes = "pending" if change is None else (
                f"{change['improved']}/{change['regressed']}/{change['tied']}"
            )
            frequency = stats["candidate_frequency_rms_hz"]
            candidate_rms = "pending" if frequency is None else f"{frequency['mean']:.3f}"
            control_rms = stats["control_frequency_rms_hz"]["mean"]
            lines.append(f"| {name} | {arm} | {changes} | "
                         f"{stats['raw_failed']}/{stats['raw_attempts']} | "
                         f"{stats['recovery_fallbacks']} | {control_rms:.3f}/{candidate_rms} |")
    lines += ["", "| Member | Session | Extra search | Status | Region failures | Fit failures |",
              "|---|---|---|---|---:|---:|"]
    for row in cases:
        member = row["member"]
        lines.append(f"| {member['inventory_label']} | {member['session_id']} | "
                     f"{row['requested']} | {row['status']} | {len(row['regional_failures'])} | "
                     f"{sum(row['raw_failed'].values())} |")
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(summary["groups"]["Pooled"]["available"], "of148 endpoints determined;",
          "complete" if summary["complete"] else "candidate full means withheld")


if __name__ == "__main__":
    main()
