"""Completion-gated phase evaluation; no references until all twelve are terminal."""

import json
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter133/report.py"))
ARMS = ("fitted-c", "zero-c")
NAMES = ("archive", "timestamp", "phase")
sha = BASE["sha"]
aggregate = BASE["aggregate"]
frequency_effects = BASE["frequency_effects"]


def load_receipts(plan, digest, folder):
    if len(plan["members"]) != 12 or len({m["label"] for m in plan["members"]}) != 12:
        raise ValueError("all twelve fixed members required")
    return BASE["load_receipts"](plan, digest, folder)


def summarize(rows):
    groups = {
        "full": rows,
        **{d: [r for r in rows if r["dataset"] == d] for d in sorted({r["dataset"] for r in rows})},
    }
    output = {}
    for group, selected in groups.items():
        output[group] = {}
        for arm in ARMS:
            pairs = [(r, r["arms"][arm]["timestamp"], r["arms"][arm]["phase"]) for r in selected]
            deltas = [
                (r["label"], p["error_km"] - t["error_km"])
                for r, t, p in pairs
                if t and p and t["qualified"] and p["qualified"]
            ]
            output[group][arm] = {
                "metrics": {name: aggregate(selected, arm, name) for name in NAMES},
                "archive_fallback_sensitivity": {
                    name: aggregate(selected, arm, name, True) for name in NAMES[1:]
                },
                "paired_phase_minus_timestamp": {
                    "expected": len(selected),
                    "qualified_pairs": len(deltas),
                    "complete_matched_coverage": len(deltas) == len(selected),
                    "improvements": sum(d < -1e-9 for _, d in deltas),
                    "regressions": sum(d > 1e-9 for _, d in deltas),
                    "regressions_over_1km": sum(d > 1 for _, d in deltas),
                    "maximum_regression_km": max([0, *(d for _, d in deltas)]),
                    "regressing_labels": [label for label, d in deltas if d > 1e-9],
                },
            }
    return output


def plot(rows, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for axes_row, arm in zip(axes, ARMS, strict=True):
        for name in NAMES:
            values = [(i, r["arms"][arm][name]) for i, r in enumerate(rows)]
            qualified = [(i, v["error_km"]) for i, v in values if v and v["qualified"]]
            if qualified:
                axes_row[0].plot(
                    [i for i, _ in qualified], [v for _, v in qualified], ".-", label=name
                )
            # ECDF only for complete arm/model coverage; never silently zero-fill.
            if len(qualified) == len(rows):
                x = np.sort([v for _, v in qualified])
                axes_row[1].plot(x, np.arange(1, len(x) + 1) / len(x), label=name)
        axes_row[0].set(title=arm, ylabel="Position error (km)")
        axes_row[0].set_xticks(
            range(len(rows)), [r["label"] for r in rows], rotation=45, ha="right"
        )
        axes_row[1].set(
            title=arm + " — complete models only",
            xlabel="Position error (km)",
            ylabel="Cumulative fraction",
        )
        for ax in axes_row:
            ax.legend()
            ax.grid(alpha=0.2)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    receipts = load_receipts(plan, sha(protocol), HERE / "results")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError("frozen source/input changed: " + name)
    # Only now may reference-bearing evaluation authority be opened.
    port = runpy.run_path(str(ROOT / "reports/2026_10_09_position_error_iter107/report.py"))
    authority_path = ROOT / "reports/2026_10_09_position_error_iter107/protocol.json"
    authority = {
        port["member_label"](m): m for m in json.loads(authority_path.read_text())["members"]
    }
    historical_path = ROOT / "reports/2026_10_10_position_error_iter130/evaluation.json"
    historical = {r["label"]: r for r in json.loads(historical_path.read_text())["members"]}
    from leo.analysis.regional_position_score import coordinates
    from leo.contracts.digests import canonical_digest
    from leo.contracts.regional_position import RegionalPrior

    rows = []
    for binding, receipt in zip(plan["members"], receipts, strict=True):
        document = port["evaluation_document"](authority[binding["label"]])
        BASE["check_evaluation_identity"](document, binding, canonical_digest)
        prior = RegionalPrior(**document["configuration"]["prior"])
        reference = (document["reference_latitude_deg"], document["reference_longitude_deg"])
        projection = json.loads((ROOT / binding["case_binding"]["projection_path"]).read_text())
        row = dict(
            label=binding["label"],
            dataset=binding["dataset"],
            status=receipt["status"],
            error=receipt.get("error"),
            integrity_failures=receipt.get("integrity_failures", []),
            arms={},
            frequency_effects={},
            attempt_failures={},
        )
        for arm in ARMS:
            row["arms"][arm] = {}
            for name in NAMES:
                attempt = receipt.get("attempts", {}).get(name, {}).get(arm)
                if name == "archive":
                    fit = projection["archive"]["stages"]["B7"][arm]
                    qualified = historical[binding["label"]]["arms"][arm]["archive"]["qualified"]
                elif (
                    receipt["status"] == "model-integrity-failed"
                    or not attempt
                    or attempt["status"] != "complete"
                ):
                    row["arms"][arm][name] = None
                    row["attempt_failures"][name + "/" + arm] = (
                        attempt.get("error", "unavailable") if attempt else "missing"
                    )
                    continue
                else:
                    fit, qualified = attempt["fit"], bool(attempt["qualified"])
                row["arms"][arm][name] = dict(
                    error_km=BASE["distance"](
                        coordinates(prior, np.asarray(fit["vector"])[:2]), reference
                    ),
                    qualified=qualified,
                    objective=fit["objective"],
                    posterior_rms_hz=fit.get("posterior_rms_hz"),
                    evaluations=fit.get("evaluations"),
                    elapsed_s=fit.get("elapsed_s"),
                    score_components=fit.get("score_components"),
                    independent_stationarity=fit.get("independent_stationarity"),
                    stop_reason=fit.get("stop_reason"),
                    reported_converged=fit.get("reported_converged"),
                )
            attempts = [receipt.get("attempts", {}).get(name, {}).get(arm) for name in NAMES[1:]]
            if receipt["status"] != "model-integrity-failed" and all(
                a and a["status"] == "complete" for a in attempts
            ):
                effect = frequency_effects(attempts[0]["fit"], attempts[1]["fit"])
                effect.update(
                    timestamp_qualified=attempts[0]["qualified"],
                    phase_qualified=attempts[1]["qualified"],
                )
            else:
                effect = dict(available=False, reason="missing/failed attempt or model integrity")
            row["frequency_effects"][arm] = effect
        rows.append(row)
    payload = dict(
        members=rows,
        groups=summarize(rows),
        runtime_sum_s=sum(r["total_elapsed_s"] for r in receipts),
    )
    (HERE / "evaluation.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    plot(rows, HERE / "comparison.png")
    lines = [
        "# Clean phase-timing replication",
        "",
        "All twelve consumed-development members are reported. Original measurements and support "
        "are unchanged; all four fits share the fitted-derived seed, with c=0 RF locks. "
        "This removes 130’s legacy reference-field admission but also changes its c=0 "
        "initialization: use the fresh timestamp control as comparator. These are neither "
        "unseen validation nor full-cohort gains. No operational model winner is selected.",
        "",
        "Archived B7 is a separate historical comparator. Its qualification provenance is the "
        "published 130 evaluator; clean 132 establishes reconstruction parity, not new endpoint "
        "qualification. Raw failures withhold complete position metrics. "
        "Archive fallback is a labelled sensitivity only.",
        "",
        "![Position errors](comparison.png)",
        "",
        "| Dataset | Arm | Model | Qualified | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, arms in payload["groups"].items():
        for arm, content in arms.items():
            for name, metrics in content["metrics"].items():
                values = [
                    f"{metrics[k]:.6f}" if k in metrics else "withheld"
                    for k in ("mean_km", "median_km", "p95_km", "worst_km")
                ]
                lines.append(
                    f"| {group} | {arm} | {name} | {metrics['qualified']}/{metrics['expected']} | "
                    + " | ".join(values)
                    + " |"
                )
    lines += [
        "",
        "| Dataset | Arm | Qualified pairs | Improved | Regressed | "
        ">1 km regressions | Max regression km |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, arms in payload["groups"].items():
        for arm, content in arms.items():
            d = content["paired_phase_minus_timestamp"]
            lines.append(
                f"| {group} | {arm} | {d['qualified_pairs']}/{d['expected']} | "
                f"{d['improvements']} | {d['regressions']} | {d['regressions_over_1km']} | "
                f"{d['maximum_regression_km']:.6f} |"
            )
    lines += [
        "",
        "Regressing labels (qualified matched pairs only; not selection criteria):",
    ]
    for group, arms in payload["groups"].items():
        for arm, content in arms.items():
            labels = content["paired_phase_minus_timestamp"]["regressing_labels"]
            lines.append(f"\n{group}, {arm}: {', '.join(labels) or 'none'}.")
    lines += [
        "",
        "Frequency fit and support remain separate from geographic accuracy. Values below are "
        "descriptive saved outputs; unqualified fits are explicitly marked. A lower phase-model "
        "objective cannot establish the physical convention or choose a model.",
        "",
        "| Member | Arm | Model | Qualified | RMS Hz | Objective | Fit seconds |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        for arm in ARMS:
            for name in NAMES[1:]:
                value = row["arms"][arm][name]
                if value:

                    def fmt(key, value=value):
                        return "unavailable" if value.get(key) is None else f"{value[key]:.6f}"

                    lines.append(
                        f"| {row['label']} | {arm} | {name} | {value['qualified']} | "
                        f"{fmt('posterior_rms_hz')} | {fmt('objective')} | {fmt('elapsed_s')} |"
                    )
                else:
                    lines.append(
                        f"| {row['label']} | {arm} | {name} | missing/failed | — | — | — |"
                    )
    lines += [
        "",
        "| Member | Arm | Changed assignments | Nonclutter mass change |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        for arm, effect in row["frequency_effects"].items():
            if effect["available"]:
                delta = (
                    effect["candidate"]["nonclutter_mass"] - effect["original"]["nonclutter_mass"]
                )
                lines.append(
                    f"| {row['label']} | {arm} | {effect['assignment_changes']} | {delta:.6f} |"
                )
            else:
                lines.append(f"| {row['label']} | {arm} | unavailable | unavailable |")
    lines += [
        "",
        f"Summed member time: {payload['runtime_sum_s']:.3f}s, including reconstruction; "
        "not parallel wall time. Peak RSS unavailable. The 90-second fit cap is soft. "
        "Score components, every failure, fallback sensitivity and per-member paired "
        "outcomes are in [evaluation.json](evaluation.json).",
        "",
        "Complete membership: "
        + ", ".join(r["label"] + " (" + r["status"] + ")" for r in rows)
        + ".",
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines))
    paths = [
        protocol,
        authority_path,
        historical_path,
        HERE / "report.py",
        HERE / "test_report.py",
        HERE / "evaluation.json",
        HERE / "comparison.png",
        HERE / "RESULTS.md",
        HERE.parent / "2026_10_10_position_error_iter133/report.py",
    ]
    paths += [HERE / "results" / (m["label"] + ".json") for m in plan["members"]]
    (HERE / "report-integrity.json").write_text(
        json.dumps({str(p.relative_to(ROOT)): sha(p) for p in paths}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
