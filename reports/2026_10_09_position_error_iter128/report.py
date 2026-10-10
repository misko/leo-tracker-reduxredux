"""Measurement reproducibility and circular changes only; no frequency ground truth."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def summarize(plan, directory=HERE):
    protocol_digest = hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest()
    members, values, failures = [], {name: [] for name in ("logparabola", "newton")}, []
    wraps = Counter()
    for binding in plan["members"]:
        label = binding["label"]
        path = directory / "results" / label / "result.json"
        if not path.exists():
            members.append(
                {"label": label, "status": "pending", "expected": binding["expected_observations"]}
            )
            continue
        receipt = json.loads(path.read_text())
        if (
            receipt["protocol_sha256"] != protocol_digest
            or receipt["metadata_sha256"] != binding["metadata_sha256"]
        ):
            raise ValueError("terminal identity differs")
        rows_path = path.parent / "rows.jsonl"
        if hashlib.sha256(rows_path.read_bytes()).hexdigest() != receipt["rows_sha256"]:
            raise ValueError("rows digest differs")
        rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
        metadata_path = HERE.parents[1] / binding["metadata_path"]
        if hashlib.sha256(metadata_path.read_bytes()).hexdigest() != binding["metadata_sha256"]:
            raise ValueError("metadata digest differs")
        metadata = json.loads(metadata_path.read_text())
        ids = [row["window_id"] for row in rows]
        if len(ids) != len(set(ids)) or set(ids) != set(metadata["window_ids"]):
            raise ValueError("original row coverage differs")
        if dict(Counter(r["status"] for r in rows)) != receipt["counts"]:
            raise ValueError("terminal counts differ")
        member = {"label": label, "sample_rate_hz": binding["sample_rate_hz"], **receipt}
        members.append(member)
        for row in rows:
            if row["status"] != "complete":
                failures.append({"label": label, **row})
                continue
            for name in values:
                change = row["result"]["changes"][name]
                values[name].append(change["circular_hz"])
                wraps[name] += int(change["wrap_count"] != 0)
    complete = all(m["status"] != "pending" for m in members)
    stats = {}
    for name, changes in values.items():
        a = np.asarray(changes)
        stats[name] = (
            None
            if not len(a)
            else {
                "count": len(a),
                "mean_signed_hz": float(a.mean()),
                "rms_change_hz": float(np.sqrt(np.mean(a**2))),
                "median_abs_hz": float(np.median(abs(a))),
                "p95_abs_hz": float(np.percentile(abs(a), 95)),
                "maximum_abs_hz": float(max(abs(a))),
                "representation_wraps": wraps[name],
            }
        )
    return {
        "coverage_complete": complete,
        "members": members,
        "failures": failures,
        "successful_rows_only_changes": stats,
        "interpretation": "Changes from original CFO, not errors or accuracy gains",
    }, values


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    summary, values = summarize(plan)
    if not summary["coverage_complete"]:
        raise ValueError("all twelve terminals required before final report")
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for name, changes in values.items():
        a = np.asarray(changes)
        if not len(a):
            continue
        axes[0].hist(a, bins=np.linspace(-225, 225, 61), histtype="step", label=name)
        x = np.sort(abs(a))
        axes[1].plot(x, np.arange(1, len(x) + 1) / len(x), label=name)
    axes[0].set(xlabel="Circular CFO change from original (Hz)", ylabel="Observations")
    axes[1].set(xlabel="Absolute circular CFO change (Hz)", ylabel="Cumulative fraction")
    for ax in axes:
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle("Original-IQ replay: 33,424 parity-qualified rows; changes, not accuracy")
    fig.tight_layout()
    fig.savefig(HERE / "changes.png", dpi=160)
    lines = [
        "# Original-observation CFO replay",
        "",
        "All twelve consumed-development recordings retain their original observation membership. "
        "No position fit, reference error, reacquisition or admission change occurred.",
        "",
        "**DS18-029 failed for 1,782 of its 2,771 observations**: 1,768 visit counter/count "
        "mismatches and 14 out-of-range reader requests. The other 989 rows passed. "
        "The adapter treated sparse event IDs as retained-visit ordinals. Public metadata "
        "shows the first difference at ordinal715→event718; mapping through the manifest "
        "predicts exactly every failed row. Guards prevented scoring the wrong IQ. "
        "All eleven other members passed. These failures remain in the frozen receipts; "
        "[the separately proposed successor](../2026_10_10_position_error_iter134/README.md) "
        "does not erase them. Full twelve-member positioning is unavailable from128 alone.",
        "",
        "| Member | Original rows | Parity passed | Other outcomes | Elapsed seconds |",
        "|---|---:|---:|---:|---:|",
    ]
    for m in summary["members"]:
        good = m["counts"].get("complete", 0)
        lines.append(
            f"| {m['label']} | {m['expected']} | {good} | {m['rows'] - good} "
            f"| {m['elapsed_s']:.2f} |"
        )
    lines += [
        "",
        "![Circular measurement changes](changes.png)",
        "",
        "Only rows passing exact frozen baseline parity contribute to change summaries. "
        "Any failures remain listed in summary.json and raw receipts; they are not replaced. "
        "Circular changes and representation wraps are reported separately. Smaller or nonzero "
        "changes do not establish more accurate real-corpus frequency estimates, "
        "and no localization gain is claimed.",
        "",
        "| Refiner | RMS change Hz | Median absolute Hz | p95 Hz | Maximum Hz | Wraps |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, stats in summary["successful_rows_only_changes"].items():
        if stats:
            lines.append(
                f"| {name} | {stats['rms_change_hz']:.3f} | {stats['median_abs_hz']:.3f} "
                f"| {stats['p95_abs_hz']:.3f} "
                f"| {stats['maximum_abs_hz']:.3f} | {stats['representation_wraps']} |"
            )
    lines += [
        "",
        "Timing includes reading and replay; per-row scorer elapsed is available separately. "
        "Peak RSS was not measured. The 1,200-second cap is soft and checked between calls. "
        "Runtime is not an embedded-device speed claim.",
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
