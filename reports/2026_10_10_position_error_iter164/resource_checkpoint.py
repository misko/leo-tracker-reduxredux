"""Publish execution-only cost checkpoints for the frozen 193-member run.

This reads no candidate positions, scores, reference coordinates, or errors.
It is reporting code outside the frozen numerical and evaluation closures.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

from batch import TERMINAL, prior_batches, validate_batches
from execute import HERE
from leo.contracts.digests import canonical_digest


def build(plan, results, index):
    members = validate_batches(plan)
    batches = plan["execution_batches"]
    if not 0 <= index < len(batches):
        raise ValueError("batch outside frozen inventory")
    digest = canonical_digest(plan)
    prior_batches(results, index + 1, digest, batches)
    receipt_phases = {}
    for number in range(index + 1):
        for shard in (0, 1):
            receipt = json.loads(
                (results / f"batch-{number}-shard-{shard}.json").read_text()
            )
            receipt_phases.update(
                (row["label"], row["phases"]) for row in receipt["members"]
            )

    rows = []
    cumulative = 0.0
    for number in range(index + 1):
        for label in batches[number]:
            if label not in members:
                raise ValueError("foreign label")
            phases = {}
            total = 0.0
            for phase in ("search", "native", "zero"):
                directory = results / label / phase
                record = json.loads((directory / "result.json").read_text())
                if record.get("protocol_sha256") != digest or record.get("label") != label:
                    raise ValueError("foreign phase result")
                if phase != "search" and record.get("branch") != phase:
                    raise ValueError("swapped continuation result")
                status = record.get("status")
                if status not in TERMINAL:
                    raise ValueError("nonterminal phase result")
                if status != receipt_phases[label][phase]:
                    raise ValueError("phase result disagrees with controller receipt")
                seconds = record.get("elapsed_s", 0.0)
                if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
                    raise ValueError("invalid elapsed time")
                slices = len(list((directory / "slices").glob("*.started.json")))
                finished_suffix = "*.finished.json" if phase == "search" else "*.done.json"
                if slices != len(list((directory / "slices").glob(finished_suffix))):
                    raise ValueError("unpaired slice receipt")
                phases[phase] = dict(status=status, slices=slices, worker_seconds=seconds)
                total += seconds
            cumulative += total
            if number == index:
                rows.append(dict(label=label, phases=phases, worker_seconds=total))

    batch_seconds = sum(row["worker_seconds"] for row in rows)
    count = sum(map(len, batches[: index + 1]))
    receipt_sha = {
        str(shard): hashlib.sha256(
            (results / f"batch-{index}-shard-{shard}.json").read_bytes()
        ).hexdigest()
        for shard in (0, 1)
    }
    return dict(
        batch=index,
        protocol_sha256=digest,
        receipt_sha256=receipt_sha,
        members=rows,
        all_phases_complete=all(
            phase["status"] == "complete"
            for row in rows for phase in row["phases"].values()
        ),
        batch_worker_seconds=batch_seconds,
        batch_mean_worker_seconds=batch_seconds / len(rows),
        cumulative_members=count,
        cumulative_worker_seconds=cumulative,
        cumulative_mean_worker_seconds=cumulative / count,
        linear_full193_worker_hours=cumulative / count * 193 / 3600,
        ideal_two_worker_hours=cumulative / count * 193 / 7200,
        position_evaluation="closed until all193 terminal",
        next_batch=(
            f"batch{index + 1} may begin after resource and integrity review"
            if index + 1 < len(batches) else "all batches terminal"
        ),
    )


def plot(record, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = record["members"]
    fig, ax = plt.subplots(figsize=(12, max(5, len(rows) * 0.42 + 1.5)))
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")
    colors = {"search": "#2563eb", "native": "#f59e0b", "zero": "#10b981"}
    left = [0.0] * len(rows)
    for phase in ("search", "native", "zero"):
        widths = [row["phases"][phase]["worker_seconds"] / 60 for row in rows]
        ax.barh(range(len(rows)), widths, left=left, color=colors[phase], label=phase)
        left = [a + b for a, b in zip(left, widths)]
    ax.set_yticks(range(len(rows)), [row["label"] for row in rows])
    ax.invert_yaxis()
    ax.set_xlabel("Recorded worker minutes per scan")
    ax.set_title(f"Batch {record['batch']}: search and two continuation fits")
    ax.grid(axis="x", alpha=0.18)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=int)
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--results", type=Path, default=HERE / "results")
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    record = build(json.loads(args.protocol.read_text()), args.results, args.batch)
    json_path = args.output / f"CHECKPOINT_{args.batch}.json"
    image_path = args.output / f"checkpoint-{args.batch}-cost.png"
    if json_path.exists() or image_path.exists():
        raise FileExistsError("checkpoint artifact already exists")
    json_path.write_text(json.dumps(record, indent=2) + "\n")
    plot(record, image_path)
    print(json.dumps({key: record[key] for key in (
        "batch", "cumulative_members", "all_phases_complete", "batch_worker_seconds",
        "cumulative_mean_worker_seconds", "receipt_sha256"
    )}, indent=2))


if __name__ == "__main__":
    main()
