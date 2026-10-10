"""Receipt-only parity coverage: no model reconstruction or truth ports."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")


def summarize(members, receipts):
    expected = {m["label"]: m for m in members}
    if len(expected) != len(members) or set(receipts) - set(expected):
        raise ValueError("Duplicate authority or unknown receipt member")
    rows = []
    for label, member in expected.items():
        value = receipts.get(label)
        if value is not None and (
            value.get("label") != label or value["status"] not in ("complete", "failed")
        ):
            raise ValueError("Invalid receipt identity/status")
        if value and value.get("optimizer_calls") != 0:
            raise ValueError("Unexpected optimizer call")
        if value and value.get("endpoint_evaluations", 0) > 2:
            raise ValueError("Endpoint evaluation cap exceeded")
        if (
            value
            and value["status"] == "complete"
            and any(value.get("arms", {}).get(a, {}).get("status") != "complete" for a in ARMS)
        ):
            raise ValueError("Complete member missing complete arms")
        if value and value["status"] == "complete":
            if value.get("endpoint_evaluations") != 2:
                raise ValueError("Complete parity requires exactly two evaluations")
            for arm in ARMS:
                a = value["arms"][arm]
                numbers = [float(a[k]) for k in ("stored", "reconstructed", "delta")]
                if not all(map(math.isfinite, numbers)) or abs(numbers[2]) > 1e-6:
                    raise ValueError("Complete arm violates parity tolerance")
        rows.append(
            dict(
                label=label,
                dataset="newer development" if label.startswith("POST18-") else label.split("-")[0],
                status="pending" if value is None else value["status"],
                receipt=value,
                membership=member["membership"],
            )
        )
    groups = {}
    for group in ("all", *sorted({r["dataset"] for r in rows})):
        subset = [r for r in rows if group == "all" or r["dataset"] == group]
        arms = {}
        for arm in ARMS:
            completed = [
                r["receipt"]["arms"][arm]
                for r in subset
                if r["receipt"]
                and r["receipt"].get("arms", {}).get(arm, {}).get("status") == "complete"
            ]
            deltas = [float(a["delta"]) for a in completed]
            if not all(math.isfinite(x) for x in deltas):
                raise ValueError("Nonfinite parity delta")
            arms[arm] = dict(
                complete=len(completed),
                missing_or_failed=len(subset) - len(completed),
                max_abs_delta=None if not deltas else max(map(abs, deltas)),
            )
        groups[group] = dict(
            members=len(subset),
            statuses=dict(Counter(r["status"] for r in subset)),
            summed_elapsed_s=sum(
                float(r["receipt"].get("elapsed_s", 0)) for r in subset if r["receipt"]
            ),
            arms=arms,
        )
    return dict(
        rows=rows,
        groups=groups,
        full_parity_verified=all(r["status"] == "complete" for r in rows),
        scope="No-fit ordinary endpoint parity only; no accuracy or phase-model result",
    )


def main():
    protocol = HERE / "parity-protocol.json"
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    plan = json.loads(protocol.read_text())
    for relative, expected in {**plan["sources"], **plan["inputs"]}.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen source/input changed: " + relative)
    receipts = {}
    receipt_hashes = {}
    for path in (HERE / "parity-results").glob("*.json"):
        if path.name.endswith(".claim.json"):
            continue
        value = json.loads(path.read_text())
        if value["protocol_sha256"] != digest or value["label"] != path.stem:
            raise ValueError("Foreign parity receipt")
        claim_path = path.with_suffix(".claim.json")
        claim = json.loads(claim_path.read_text())
        if claim["label"] != path.stem or claim["protocol_sha256"] != digest:
            raise ValueError("Foreign parity claim")
        for artifact in (path, claim_path):
            receipt_hashes[str(artifact.relative_to(HERE))] = hashlib.sha256(
                artifact.read_bytes()
            ).hexdigest()
        receipts[path.stem] = value
    result = summarize(plan["members"], receipts)
    if len(plan["members"]) != 193 or any(r["status"] == "pending" for r in result["rows"]):
        raise ValueError(
            "Final report requires all 193 terminal receipts; failures remain included"
        )
    result.update(protocol_sha256=digest, receipt_sha256=receipt_hashes)
    plot(result, HERE / "parity-diagnostics.png")
    (HERE / "parity-summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    lines = [
        "# Selected endpoint parity coverage",
        "",
        result["scope"],
        "",
        "![Parity coverage and cost](parity-diagnostics.png)",
        "",
        "| Dataset | Members | Complete | Failed | Pending | Fitted max delta "
        "| Zero-c max delta | Summed seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group, row in result["groups"].items():
        s = row["statuses"]
        lines.append(
            f"| {group} | {row['members']} | {s.get('complete', 0)} | {s.get('failed', 0)} "
            f"| {s.get('pending', 0)} | {row['arms']['fitted-c']['max_abs_delta']} "
            f"| {row['arms']['zero-c']['max_abs_delta']} | {row['summed_elapsed_s']:.3f} |"
        )
    lines += [
        "",
        "Summed runtime is processing cost, not elapsed wall time. "
        "Partial coverage does not establish full-cohort parity.",
        "",
        "| Member | Status |",
        "|---|---|",
    ]
    lines += [f"| {r['label']} | {r['status']} |" for r in result["rows"]]
    (HERE / "PARITY_RESULTS.md").write_text("\n".join(lines) + "\n")


def plot(result, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    groups = [(k, v) for k, v in result["groups"].items() if k != "all"]
    bottom = np.zeros(len(groups))
    for status, color in (("complete", "#359b73"), ("failed", "#d26b54"), ("pending", "#b9b9b9")):
        counts = [v["statuses"].get(status, 0) for _, v in groups]
        axes[0].bar(range(len(groups)), counts, bottom=bottom, label=status, color=color)
        bottom += counts
    axes[0].set_xticks(range(len(groups)), [k for k, _ in groups], rotation=25, ha="right")
    axes[0].set(title="Membership coverage", ylabel="Recordings")
    axes[0].legend()
    for arm in ARMS:
        values = [
            (i, abs(r["receipt"]["arms"][arm]["delta"]))
            for i, r in enumerate(result["rows"])
            if r["receipt"]
            and r["receipt"].get("arms", {}).get(arm, {}).get("status") == "complete"
        ]
        axes[1].scatter([i for i, _ in values], [v for _, v in values], s=12, label=arm)
    axes[1].axhline(1e-6, linestyle="--", color="grey", label="Admission tolerance")
    axes[1].set(
        title="Saved objective parity",
        xlabel="Frozen member index",
        ylabel="Absolute objective delta",
    )
    axes[1].legend()
    costs = [
        (i, r["receipt"]["elapsed_s"])
        for i, r in enumerate(result["rows"])
        if r["receipt"] and "elapsed_s" in r["receipt"]
    ]
    axes[2].scatter([i for i, _ in costs], [v for _, v in costs], s=12)
    axes[2].set(
        title="Per-member reconstruction cost",
        xlabel="Frozen member index",
        ylabel="Processing seconds",
    )
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
