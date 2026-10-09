"""Post-census descriptive reporting; imports no inference or reference data."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")
CONFIDENCE = (
    "confidence_below_half",
    "confidence_half_to_nine_tenths",
    "confidence_at_least_nine_tenths",
)


def aggregate(rows, arm):
    populations = {}
    for name in ("all", "linked", "independent"):
        values = [r["arms"][arm]["ambiguity"]["populations"][name] for r in rows]
        count = sum(v["rows"] for v in values)
        populations[name] = dict(
            rows=count,
            mean_entropy_nats=sum(
                v["entropy_nats"]["mean"] * v["rows"] for v in values if v["rows"]
            )
            / count
            if count
            else None,
            mean_maximum_probability=sum(
                v["maximum_probability"]["mean"] * v["rows"] for v in values if v["rows"]
            )
            / count
            if count
            else None,
            confidence_counts={k: sum(v[k] for v in values) for k in CONFIDENCE},
            confidence_fractions={
                k: sum(v[k] for v in values) / count if count else None for k in CONFIDENCE
            },
        )
    fractions = [
        r["arms"][arm]["ambiguity"]["populations"]["linked"]["rows"]
        / r["arms"][arm]["ambiguity"]["populations"]["all"]["rows"]
        for r in rows
        if r["arms"][arm]["ambiguity"]["populations"]["all"]["rows"]
    ]
    switches = [r["arms"][arm]["ambiguity"]["switches"] for r in rows]
    total = populations["all"]["rows"]
    return dict(
        recordings=len(rows),
        rows=total,
        populations=populations,
        linked_fraction=populations["linked"]["rows"] / total if total else None,
        linked_fraction_per_recording=dict(
            count=len(fractions),
            median=float(np.median(fractions)) if fractions else None,
            p95=float(np.percentile(fractions, 95)) if fractions else None,
            min=min(fractions) if fractions else None,
            max=max(fractions) if fractions else None,
        ),
        mean_entropy_nats=populations["all"]["mean_entropy_nats"],
        confidence_fractions=populations["all"]["confidence_fractions"],
        switches={k: sum(s[k] for s in switches) for k in switches[0]},
        max_abs_objective_delta=max(abs(r["arms"][arm]["objective_delta"]) for r in rows),
        max_abs_rho0_whole_score_delta=max(
            abs(r["arms"][arm]["rho0_whole_score_delta"]) for r in rows
        ),
        max_rho0_prediction_gradient_abs=max(
            r["arms"][arm]["rho0_prediction_gradient_max_abs"] for r in rows
        ),
    )


def summarize(plan, receipts, digest):
    statuses, valid = [], []
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        receipt = receipts.get(label)
        status = "missing" if receipt is None else receipt["status"]
        if receipt is not None:
            assert receipt["protocol_sha256"] == digest
            assert receipt["member"] == member
        if status == "complete":
            assert set(receipt["arms"]) == set(ARMS)
            valid.append(receipt)
        statuses.append(
            dict(
                label=label,
                dataset=member["dataset"],
                status=status,
                error=None if receipt is None else receipt.get("error"),
            )
        )
    complete = len(valid) == len(statuses)
    output = dict(
        complete=complete,
        membership=statuses,
        expected=len(statuses),
        completed=len(valid),
        metrics=None,
    )
    if not complete:
        return output
    metrics = {}
    for dataset in sorted({row["dataset"] for row in statuses}):
        rows = [r for r in valid if r["member"]["dataset"] == dataset]
        metrics[dataset] = {arm: aggregate(rows, arm) for arm in ARMS}
    output["metrics"] = metrics
    output["pooled"] = {arm: aggregate(valid, arm) for arm in ARMS}
    output["runtime"] = dict(
        sum_recording_elapsed_s=sum(r["elapsed_s"] for r in valid),
        wall_time_s=None,
        explanation="Sum of receipt elapsed times includes loading and both arms; "
        "concurrent wall time is not recorded by these receipts.",
    )
    return output


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    receipts = {p.stem: json.loads(p.read_text()) for p in (HERE / "results").glob("*.json")}
    summary = summarize(plan, receipts, digest)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Independent-likelihood ambiguity census",
        "",
        f"Coverage: {summary['completed']}/{summary['expected']} complete.",
        "",
        "This describes consumed-data categorical ambiguity at archived B7 endpoints. "
        "It measures no position improvement or physical association correctness.",
        "",
    ]
    if summary["complete"]:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(15, 9))
        datasets = list(summary["metrics"])
        for index, arm in enumerate(ARMS):
            x = list(range(len(datasets)))
            data = [summary["metrics"][d][arm] for d in datasets]
            axes[index, 0].bar(
                x,
                [
                    d["populations"]["linked"]["mean_entropy_nats"]
                    if d["populations"]["linked"]["rows"]
                    else np.nan
                    for d in data
                ],
            )
            bottom = [0.0] * len(data)
            for key, label in zip(CONFIDENCE, ("<0.5", "0.5–0.9", "≥0.9"), strict=True):
                values = [
                    d["populations"]["linked"]["confidence_fractions"][key] or 0 for d in data
                ]
                axes[index, 1].bar(x, values, bottom=bottom, label=label)
                bottom = [a + b for a, b in zip(bottom, values, strict=True)]
            bottom = [0.0] * len(data)
            for key in ("confident_satellite_switches", "weak_or_clutter_switches"):
                values = [d["switches"][key] / max(1, d["switches"]["links"]) for d in data]
                axes[index, 2].bar(x, values, bottom=bottom, label=key.replace("_", " "))
                bottom = [a + b for a, b in zip(bottom, values, strict=True)]
            for col, title in enumerate(
                (
                    "Linked entropy (nats)",
                    "Linked confidence fractions",
                    "Switch categories / links",
                )
            ):
                axes[index, col].set_title(f"{arm}: {title}")
                axes[index, col].set_xticks(x, datasets)
                if col:
                    axes[index, col].legend(fontsize=9)
        fig.suptitle("Archived B7 ambiguity: descriptive, not association correctness")
        fig.tight_layout()
        fig.savefig(HERE / "ambiguity.png", dpi=160)
        plt.close(fig)
        lines += [
            "![Descriptive matched-arm census](ambiguity.png)",
            "",
            "Entropy is a row-weighted mean; confidence and switch categories are "
            "descriptive, not calibrated uncertainty or independent samples.",
            "",
        ]
        lines += [
            "|Cohort|Arm|All / linked / independent rows|"
            "Linked fraction median / p95 / min / max|Linked entropy|Linked mean confidence|",
            "|---|---|---|---|---|---|",
        ]
        for dataset, data in [("Pooled", summary["pooled"]), *summary["metrics"].items()]:
            for arm, d in data.items():
                p = d["populations"]
                coverage = d["linked_fraction_per_recording"]

                def fmt(v):
                    return "NA" if v is None else f"{v:.4g}"

                fractions = " / ".join(fmt(coverage[k]) for k in ("median", "p95", "min", "max"))
                lines.append(
                    f"|{dataset}|{arm}|{p['all']['rows']} / {p['linked']['rows']} / "
                    f"{p['independent']['rows']}|{fractions}|"
                    f"{fmt(p['linked']['mean_entropy_nats'])}|"
                    f"{fmt(p['linked']['mean_maximum_probability'])}|"
                )
        lines += [
            "",
            f"Sum of recording elapsed costs: "
            f"{summary['runtime']['sum_recording_elapsed_s']:.3f} seconds; "
            "concurrent wall time is unavailable from individual receipts.",
            "",
            "Population-specific confidence counts/fractions, entropy, maximum score/gradient "
            "parity differences and coverage are in [summary.json](summary.json). "
            "Empty linked populations have null means and fractions; "
            "zero-height plot bars mean no linked rows, not certainty.",
            "",
        ]
        lines += [
            "|Arm|Max absolute saved score delta|Max absolute rho=0 score delta|"
            "Max gradient difference|",
            "|---|---|---|---|",
        ]
        for arm, data in summary["pooled"].items():
            lines.append(
                f"|{arm}|{data['max_abs_objective_delta']:.6g}|"
                f"{data['max_abs_rho0_whole_score_delta']:.6g}|"
                f"{data['max_rho0_prediction_gradient_abs']:.6g}|"
            )
        lines.append("")
    else:
        lines += ["Full-dataset metrics and plots are withheld until every member completes.", ""]
    lines += ["|Member|Dataset|Status|", "|---|---|---|"]
    lines += [f"|{r['label']}|{r['dataset']}|{r['status']}|" for r in summary["membership"]]
    lines += ["", "[All statuses and explicit failures](summary.json)", ""]
    (HERE / "RESULTS.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
