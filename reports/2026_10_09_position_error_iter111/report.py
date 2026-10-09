"""Reporting-only conditional diagnostic; no recording or reference loader."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")


def distribution(values):
    if not np.isfinite(values).all():
        raise ValueError("nonfinite diagnostic statistic")
    return (
        dict(
            count=len(values),
            median=float(np.median(values)),
            p95=float(np.percentile(values, 95)),
            minimum=float(min(values)),
            maximum=float(max(values)),
        )
        if values
        else dict(count=0, median=None, p95=None, minimum=None, maximum=None)
    )


def summarize(plan, receipts, digest):
    labels = {b["member"]["inventory_label"] for b in plan["members"]}
    if not set(receipts) <= labels:
        raise ValueError("receipt label outside frozen pilot")

    def finite(value):
        if isinstance(value, dict):
            for nested in value.values():
                finite(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                finite(nested)
        elif isinstance(value, (float, np.floating)) and not np.isfinite(value):
            raise ValueError("nonfinite receipt value")

    rows = []
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        receipt = receipts.get(label)
        if receipt is not None:
            if receipt["status"] not in ("complete", "failed"):
                raise ValueError("nonterminal receipt status")
            finite(receipt)
            assert receipt["member"] == member and receipt["protocol_sha256"] == digest
            if receipt["status"] == "complete":
                assert set(receipt["arms"]) == set(ARMS)
        rows.append(
            dict(
                member=member,
                status="missing" if receipt is None else receipt["status"],
                error=None if receipt is None else receipt.get("error"),
                receipt=receipt,
            )
        )
    complete = [r for r in rows if r["status"] == "complete"]
    full = len(complete) == len(rows)
    result = dict(
        scope="Frozen random12 conditional diagnostic; potential148 authority retained; "
        "consumed development, not full148 or position-accuracy evaluation",
        expected=len(rows),
        potential_members=len(plan["potential_members"]),
        completed=len(complete),
        full_complete=full,
        members=rows,
        failure_counts=dict(
            resource=sum("MemoryError" in (r["error"] or "") for r in rows),
            other=sum(
                r["status"] == "failed" and "MemoryError" not in (r["error"] or "") for r in rows
            ),
            missing=sum(r["status"] == "missing" for r in rows),
        ),
        metrics=None,
        runtime_sum_s=sum(r["receipt"].get("elapsed_s", 0) for r in rows if r["receipt"]),
        wall_time_s=None,
    )
    if not full:
        return result
    result["metrics"] = {}
    for arm in ARMS:
        records = [r["receipt"]["arms"][arm] for r in complete]
        metrics = {}
        for category in ("raw", "projected"):
            metrics[category] = dict(
                singular_values=[
                    distribution([r["data_only"][category]["singular_values"][i] for r in records])
                    for i in range(2)
                ],
                ranks={
                    str(i): sum(r["data_only"][category]["rank"] == i for r in records)
                    for i in range(3)
                },
            )
        eigen = [np.asarray(r["spatial_block_eigenvalues"]["observed_local"]) for r in records]
        fractions = []
        for r in records:
            trace = np.trace(r["spatial_blocks"]["complete"])
            fractions.append(
                None
                if trace <= 0
                else float(np.trace(r["spatial_blocks"]["missing_information"]) / trace)
            )
        metrics["fixed_nuisance_observed"] = dict(
            eigenvalues=[distribution([x[i] for x in eigen]) for i in range(2)],
            negative_eigenvalue_records=int(sum(np.any(x < 0) for x in eigen)),
            missing_information_trace_fraction=distribution(
                [x for x in fractions if x is not None]
            ),
            undefined_fraction_records=sum(x is None for x in fractions),
        )
        metrics["nuisance_ranks"] = distribution([r["data_only"]["nuisance_rank"] for r in records])
        result["metrics"][arm] = metrics
    return result


def plot(summary, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    complete = [r for r in summary["members"] if r["status"] == "complete"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    labels = [r["member"]["inventory_label"] for r in complete]
    for index, arm in enumerate(ARMS):
        for category, style in (("raw", "o-"), ("projected", "x-")):
            values = [
                r["receipt"]["arms"][arm]["data_only"][category]["singular_values"][1]
                for r in complete
            ]
            axes[index, 0].plot(range(len(values)), values, style, label=category)
        for i in range(2):
            values = [
                r["receipt"]["arms"][arm]["spatial_block_eigenvalues"]["observed_local"][i]
                for r in complete
            ]
            axes[index, 1].plot(range(len(values)), values, "o-", label=f"eigenvalue{i + 1}")
        axes[index, 0].set_title(f"{arm}: weaker data-only singular value")
        axes[index, 0].set_ylabel("1/km")
        axes[index, 1].set_title(f"{arm}: fixed-nuisance affine observed eigenvalues")
        axes[index, 1].set_ylabel("1/km²")
        axes[index, 1].axhline(0, color="black", linewidth=0.7)
        for axis in axes[index]:
            axis.set_xticks(range(len(labels)), labels, rotation=60, ha="right", fontsize=8)
            axis.legend(fontsize=9)
    fig.suptitle(
        f"Conditional diagnostic: {len(complete)}/{summary['expected']} complete; "
        "no covariance claim"
    )
    fig.tight_layout()
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    receipts = {p.stem: json.loads(p.read_text()) for p in (HERE / "results").glob("*.json")}
    summary = summarize(plan, receipts, hashlib.sha256(protocol.read_bytes()).hexdigest())
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    plot(summary, HERE / "observability.png")
    lines = [
        "# Conditional endpoint observability diagnostic",
        "",
        summary["scope"],
        "",
        f"Coverage {summary['completed']}/{summary['expected']}; "
        f"failures {summary['failure_counts']}.",
        "",
        "![Per-member diagnostic](observability.png)",
        "",
        "Plots show complete receipts only; missing or failed members are not imputed. "
        "Full12 distributions are withheld unless all12 complete. Priors remain separate, "
        "bounds are omitted, and observed eigenvalues fix nuisance and omit nonlinear "
        "frequency second derivatives. Fixed-nuisance observed blocks and nuisance-relaxed "
        "complete-label projections have different conditioning and are not interchangeable. "
        "No inverse, covariance, accuracy or full148 claim.",
        "",
        f"Sum of terminal receipt elapsed costs {summary['runtime_sum_s']:.3f}s; "
        "concurrent wall time unavailable.",
        "",
        "|Member|Dataset|Status|Failure|",
        "|---|---|---|---|",
    ]
    lines += [
        f"|{r['member']['inventory_label']}|{r['member']['dataset']}|"
        f"{r['status']}|{r['error'] or ''}|"
        for r in summary["members"]
    ]
    lines += ["", "[All matrices, distributions and explicit status coverage](summary.json)", ""]
    (HERE / "RESULTS.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
