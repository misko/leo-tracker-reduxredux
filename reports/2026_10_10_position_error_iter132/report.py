"""Report saved clean-admission parity receipts only; no models or reference port."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    for name, expected in plan["sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Frozen input/source changed: " + name)
    receipts = []
    for binding in plan["members"]:
        path = HERE / "results" / (binding["label"] + ".json")
        row = json.loads(path.read_text())
        if row["label"] != binding["label"] or row["protocol_sha256"] != sha(protocol):
            raise ValueError("Foreign parity receipt")
        if row["status"] not in ("complete", "failed") or row["optimizer_calls"] != 0:
            raise ValueError("Wrong parity scope/status")
        if (
            row["status"] == "complete"
            and row["input_binding"] != binding["expected_input_binding"]
        ):
            raise ValueError("Physical signature differs")
        receipts.append(row)
    complete = [r for r in receipts if r["status"] == "complete"]
    summary = dict(
        expected=12,
        terminal=len(receipts),
        complete=len(complete),
        failed=len(receipts) - len(complete),
        optimizer_calls=0,
        runtime_sum_s=sum(r["elapsed_s"] for r in receipts),
        maximum_abs_objective_delta={
            a: max((abs(r["arms"][a]["delta"]) for r in complete), default=None)
            for a in ("fitted-c", "zero-c")
        },
        members=receipts,
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    for offset, arm in ((-0.15, "fitted-c"), (0.15, "zero-c")):
        xs = [i + offset for i, row in enumerate(receipts) if row["status"] == "complete"]
        values = [abs(row["arms"][arm]["delta"]) for row in receipts if row["status"] == "complete"]
        ax.bar(xs, values, width=0.3, label=arm)
    ax.axhline(1e-6, color="black", linestyle="--", label="Frozen parity tolerance")
    maximum = max(
        (abs(row["arms"][arm]["delta"]) for row in complete for arm in ("fitted-c", "zero-c")),
        default=0,
    )
    ax.set_ylim(0, max(1.2e-6, maximum * 1.2))
    if complete and maximum == 0:
        ax.text(
            0.5,
            0.5,
            "All saved objective differences are exactly zero",
            transform=ax.transAxes,
            ha="center",
        )
    ax.set_ylabel("Absolute saved objective difference")
    ax.set_xticks(range(len(receipts)), [r["label"] for r in receipts], rotation=45, ha="right")
    ax.set_title("Clean ordinary endpoint reconstruction; failed members are not imputed")
    ax.legend()
    fig.savefig(HERE / "parity.png", dpi=150)
    plt.close(fig)
    lines = [
        "# Clean ordinary endpoint reconstruction",
        "",
        f"All twelve members terminal: {len(complete)} complete, {12 - len(complete)} failed. "
        "Both c arms use the same clean physical reconstruction. Zero optimizer calls; "
        "no reference coordinates or errors entered runtime admission.",
        "",
        "![Saved objective parity](parity.png)",
        "",
        "| Member | Status | Fitted delta | Zero-c delta | Runtime s |",
        "|---|---|---:|---:|---:|",
    ]
    for row in receipts:
        deltas = [
            f"{row['arms'][a]['delta']:.12g}" if row["status"] == "complete" else "failed"
            for a in ("fitted-c", "zero-c")
        ]
        lines.append(
            f"| {row['label']} | {row['status']} | {deltas[0]} | {deltas[1]} | "
            f"{row['elapsed_s']:.3f} |"
        )
    lines += [
        "",
        "The five saved physical signatures were verified by the public131 loader. "
        "Regional session/input/analysis identity and saved ordinary objectives were checked. "
        "This establishes clean reconstruction parity, not fresh optimizer qualification, "
        "new position accuracy, or proof of the phase convention. Iteration130 remains "
        "a consumed diagnostic with inherited evaluation-field admission; it is not relabelled.",
        "",
        "Metadata preparation verified original source receipts as provenance before "
        "whitelisting. Runtime identity binds only sanitized inference fields. "
        "Summed elapsed time includes input reconstruction; it is not parallel wall time.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    artifacts = [
        protocol,
        HERE / "report.py",
        HERE / "summary.json",
        HERE / "parity.png",
        HERE / "RESULTS.md",
    ]
    artifacts += list((HERE / "results").glob("*.json"))
    integrity = {str(path.relative_to(ROOT)): sha(path) for path in artifacts}
    (HERE / "report-integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")


if __name__ == "__main__":
    main()
