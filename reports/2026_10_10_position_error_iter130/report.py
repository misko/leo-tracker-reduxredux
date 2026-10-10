"""Postfit matched reporting; truth only after all frozen member receipts exist."""

import hashlib
import json
import math
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def distance(position, reference):
    a, b, c, d = map(math.radians, (*position, *reference))
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, h))))


def aggregate(rows, arm, name, fallback=False):
    selected = []
    fallback_count = 0
    for row in rows:
        value = row["arms"][arm][name]
        if value is None or not value["qualified"]:
            if fallback:
                value = row["arms"][arm]["archive"]
                fallback_count += 1
            else:
                continue
        if value is not None and value["qualified"]:
            selected.append(value["error_km"])
    result = {
        "expected": len(rows),
        "qualified": len(selected),
        "fallbacks": fallback_count,
        "position_metrics_withheld": len(selected) != len(rows),
    }
    if len(selected) == len(rows):
        result.update(
            mean_km=float(np.mean(selected)),
            median_km=float(np.median(selected)),
            p95_km=float(np.quantile(selected, 0.95)),
            worst_km=max(selected),
        )
    return result


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    receipts = []
    for binding in plan["members"]:
        label = binding["member"]["inventory_label"]
        path = HERE / "results" / f"{label}.json"
        assert path.exists(), f"not terminal: {label}"
        row = json.loads(path.read_text())
        assert row["member"] == binding["member"] and row["protocol_sha256"] == digest
        assert row["status"] in ("complete", "failed", "attempt-failed")
        receipts.append(row)
    # No reference authority opened until every member has a terminal receipt.
    port = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter107/report.py"))
    full = json.loads((HERE.parent / "2026_10_09_position_error_iter107/protocol.json").read_text())
    authority = {port["member_label"](m): m for m in full["members"]}
    from leo.analysis.regional_position_score import coordinates
    from leo.contracts.regional_position import RegionalPrior

    results = []
    for row in receipts:
        label = row["member"]["inventory_label"]
        document = port["evaluation_document"](authority[label])
        prior = RegionalPrior(**document["configuration"]["prior"])
        reference = [document["reference_latitude_deg"], document["reference_longitude_deg"]]
        item = {
            "label": label,
            "dataset": row["member"]["dataset"],
            "status": row["status"],
            "failures": row["failures"],
            "arms": {},
        }
        for arm in ("fitted-c", "zero-c"):
            attempts = row["attempts"].get(arm, {})
            item["arms"][arm] = {}
            for name in ("archive", "control", "phase"):
                attempt = attempts.get(name)
                if attempt is None or (name != "archive" and attempt["status"] != "complete"):
                    item["arms"][arm][name] = None
                    continue
                fit = attempt if name == "archive" else attempt["fit"]
                latlon = coordinates(prior, np.asarray(fit["vector"])[:2])
                item["arms"][arm][name] = {
                    "error_km": distance(latlon, reference),
                    "qualified": bool(fit["converged"]),
                    "objective": fit["objective"],
                    "posterior_rms_hz": fit.get("posterior_rms_hz"),
                    "evaluations": fit.get("evaluations"),
                    "fit_elapsed_s": fit.get("elapsed_s"),
                    "stationarity": fit.get("independent_stationarity"),
                    "components": fit.get("score_components"),
                }
        results.append(item)
    summary = {}
    for arm in ("fitted-c", "zero-c"):
        summary[arm] = {}
        for name in ("archive", "control", "phase"):
            values = [r["arms"][arm][name] for r in results]
            qualified = [v for v in values if v is not None and v["qualified"]]
            entry = {
                "present": sum(v is not None for v in values),
                "qualified": len(qualified),
                "full12_position_metrics_withheld": len(qualified) != 12,
            }
            if len(qualified) == 12:
                errors = [v["error_km"] for v in qualified]
                entry.update(
                    mean_km=float(np.mean(errors)),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.quantile(errors, 0.95)),
                    worst_km=max(errors),
                )
            summary[arm][name] = entry
    payload = {
        "coverage": len(receipts),
        "members": results,
        "summary": summary,
        "runtime_sum_s": sum(r["elapsed_s"] for r in receipts),
        "scope": "Consumed diagnostic with inherited evaluation-field provenance admission; no fully reference-free execution claim; archive fallback separate",
    }
    groups = {
        "full": results,
        **{
            d: [r for r in results if r["dataset"] == d]
            for d in sorted({r["dataset"] for r in results})
        },
    }
    payload["group_metrics"] = {
        d: {
            a: {name: aggregate(rows, a, name) for name in ("archive", "control", "phase")}
            for a in ("fitted-c", "zero-c")
        }
        for d, rows in groups.items()
    }
    payload["fallback_sensitivity"] = {
        d: {
            a: {name: aggregate(rows, a, name, True) for name in ("control", "phase")}
            for a in ("fitted-c", "zero-c")
        }
        for d, rows in groups.items()
    }
    payload["paired_regressions"] = {}
    for group, rows in groups.items():
        payload["paired_regressions"][group] = {}
        for arm in ("fitted-c", "zero-c"):
            pairs = [(r["arms"][arm]["control"], r["arms"][arm]["phase"]) for r in rows]
            delta = [
                p["error_km"] - c["error_km"]
                for c, p in pairs
                if c and p and c["qualified"] and p["qualified"]
            ]
            payload["paired_regressions"][group][arm] = {
                "matched_qualified": len(delta),
                "regressions": sum(d > 1e-9 for d in delta),
                "improvements": sum(d < -1e-9 for d in delta),
                "max_regression_km": None if not delta else max(delta),
            }
    (HERE / "evaluation.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), layout="constrained")
    for axis, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        for name in ("archive", "control", "phase"):
            axis.plot(
                [r["label"] for r in results],
                [
                    np.nan
                    if r["arms"][arm][name] is None or not r["arms"][arm][name]["qualified"]
                    else r["arms"][arm][name]["error_km"]
                    for r in results
                ],
                marker="o",
                label=name,
            )
            bad = [
                r for r in results if r["arms"][arm][name] and not r["arms"][arm][name]["qualified"]
            ]
            if bad:
                axis.scatter(
                    [r["label"] for r in bad],
                    [r["arms"][arm][name]["error_km"] for r in bad],
                    marker="x",
                    label=f"{name} unqualified",
                )
        axis.set(title=arm, ylabel="Position error km")
        axis.tick_params(axis="x", rotation=65, labelsize=8)
        axis.legend()
    fig.savefig(HERE / "comparison.png", dpi=140)
    plt.close(fig)
    text = [
        "# Matched phase timing sensitivity",
        "",
        "**Diagnostic admission limitation:** the inherited legacy loader asserts equality of an archived horizontal position error field. It does not guide numerical starts or ranking, but this execution is not fully reference-free admission. See [exact dependency audit](REFERENCE_DEPENDENCY_AUDIT.md).",
        "",
        "All12 terminal member receipts are accounted. Fresh control and phase fits share ordinary archived starts, inputs, priors and budgets; archive is a separate fallback comparator. Position metrics are withheld unless all12 raw endpoints qualify. Frequency scores belong to different physical models and cannot choose the convention alone.",
        "",
        "![Matched position effects](comparison.png)",
        "",
        "|Arm|Model|Present|Qualified|Mean km|Median km|p95 km|Worst km|",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, models in summary.items():
        for name, s in models.items():
            text.append(
                f"|{arm}|{name}|{s['present']}|{s['qualified']}|"
                + "|".join(
                    "withheld" if k not in s else f"{s[k]:.4f}"
                    for k in ("mean_km", "median_km", "p95_km", "worst_km")
                )
                + "|"
            )
    text += [
        "",
        "|Dataset|Arm|Model|Expected|Qualified|Mean km|Median km|p95 km|Worst km|",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for group, arms in payload["group_metrics"].items():
        for arm, models in arms.items():
            for name, s in models.items():
                text.append(
                    f"|{group}|{arm}|{name}|{s['expected']}|{s['qualified']}|"
                    + "|".join(
                        "withheld" if k not in s else f"{s[k]:.4f}"
                        for k in ("mean_km", "median_km", "p95_km", "worst_km")
                    )
                    + "|"
                )
    text += [
        "",
        "Explicit archive-fallback sensitivity (reported, not an operational model choice):",
        "",
        "|Dataset|Arm|Model|Fallbacks|Mean km|Median km|p95 km|Worst km|",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, arms in payload["fallback_sensitivity"].items():
        for arm, models in arms.items():
            for name, s in models.items():
                text.append(
                    f"|{group}|{arm}|{name}|{s['fallbacks']}|"
                    + "|".join(
                        "withheld" if k not in s else f"{s[k]:.4f}"
                        for k in ("mean_km", "median_km", "p95_km", "worst_km")
                    )
                    + "|"
                )
    text += [
        "",
        "[All members, qualification and frequency effects](evaluation.json). No truth guided starts or winner selection, and no production change.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(text) + "\n")


if __name__ == "__main__":
    main()
