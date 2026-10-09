"""Post-census descriptive reporting; imports no inference or reference data."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")


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
        metrics[dataset] = {}
        for arm in ARMS:
            populations = [r["arms"][arm]["ambiguity"]["populations"] for r in rows]
            total = sum(p["all"]["rows"] for p in populations)
            switches = [r["arms"][arm]["ambiguity"]["switches"] for r in rows]
            metrics[dataset][arm] = dict(
                recordings=len(rows),
                rows=total,
                linked_fraction=sum(p["linked"]["rows"] for p in populations) / total,
                mean_entropy_nats=sum(
                    p["all"]["entropy_nats"]["mean"] * p["all"]["rows"] for p in populations
                )
                / total,
                confidence_fractions={
                    key: sum(p["all"][key] for p in populations) / total
                    for key in (
                        "confidence_below_half",
                        "confidence_half_to_nine_tenths",
                        "confidence_at_least_nine_tenths",
                    )
                },
                switches={key: sum(s[key] for s in switches) for key in switches[0]},
            )
    output["metrics"] = metrics
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

        fig, axes = plt.subplots(1, 4, figsize=(15, 4))
        datasets = list(summary["metrics"])
        for index, arm in enumerate(ARMS):
            x = [i + (index - 0.5) * 0.3 for i in range(len(datasets))]
            data = [summary["metrics"][d][arm] for d in datasets]
            axes[0].bar(x, [d["linked_fraction"] for d in data], 0.3, label=arm)
            axes[1].bar(x, [d["mean_entropy_nats"] for d in data], 0.3, label=arm)
            bottom = [0.0] * len(data)
            for key in data[0]["confidence_fractions"]:
                values = [d["confidence_fractions"][key] for d in data]
                axes[2].bar(x, values, 0.3, bottom=bottom, label=f"{arm}: {key}")
                bottom = [a + b for a, b in zip(bottom, values, strict=True)]
            bottom = [0.0] * len(data)
            for key in ("confident_satellite_switches", "weak_or_clutter_switches"):
                values = [d["switches"][key] / max(1, d["switches"]["links"]) for d in data]
                axes[3].bar(x, values, 0.3, bottom=bottom, label=f"{arm}: {key}")
                bottom = [a + b for a, b in zip(bottom, values, strict=True)]
        for axis, title in zip(
            axes,
            (
                "Linked row fraction",
                "Row-weighted entropy (nats)",
                "Confidence fractions",
                "Switch categories / links",
            ),
            strict=True,
        ):
            axis.set_title(title)
            axis.set_xticks(range(len(datasets)), datasets)
            axis.legend(fontsize=5)
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
    else:
        lines += ["Full-dataset metrics and plots are withheld until every member completes.", ""]
    lines += ["|Member|Dataset|Status|", "|---|---|---|"]
    lines += [f"|{r['label']}|{r['dataset']}|{r['status']}|" for r in summary["membership"]]
    lines += ["", "[All statuses and explicit failures](summary.json)", ""]
    (HERE / "RESULTS.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
