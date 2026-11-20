"""Verify and publish the saved-IQ detector comparison without replaying the archive."""

import argparse
import io
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import distribution
from . import incremental_rescue_eval as run
from . import scout_stage_figures as plot
from .prefix_figures import csv_file

TITLE = "Search one new timing region only on stock-negative receivers"
LABELS = ("Stock wide", "Full rescue", "Incremental rescue", "One-region sham")
COLORS = (plot.BASE, plot.DIAGNOSTIC, plot.CANDIDATE, "#6E74A2")


def measured(data):
    roster = run.original.load(data / "source-lock.json.gz")
    for name, digest in roster["sources"].items():
        whole_iq.checked(ROOT / name, digest)
    rows, controls = [], []
    for edge in ("lower", "upper"):
        results = run.original.load(data / f"{edge}.json.gz")
        if results["edge"] != edge or results["lock_sha256"] != run._digest(encoded(roster)):
            raise ValueError("detector receipt has different antenna or prospective roster")
        for prior, actual in zip(
            (r for r in roster["capture"] if r["edge"] == edge), results["measured"], strict=True
        ):
            if any(actual[key] != value for key, value in prior.items()):
                raise ValueError("detector case differs from frozen authentic waveform")
            rows.append(actual)
        controls.extend(
            dict(row, control=name, edge=edge) for name, row in results["controls"].items()
        )
    return rows, controls


def brief(row):
    return dict(
        gates={k: sum(v) for k, v in row["gate_counts"].items()},
        physical_gates={
            k: sum(v["physical_passes"] for v in items)
            for k, items in row["target_results"].items()
        },
        decisions=[v["decision"] for v in row["traces"]["incremental"]],
        target_count=row["target_count"],
    )


def aggregate(rows, controls):
    valid = [row for row in rows if row["status"] == "processed"]
    lanes = [
        dict(case=row["case"], visit=row["visit"], edge=row["edge"], **detail)
        for row in valid
        for detail in row["traces"]["incremental"]
    ]
    all_times = [
        dict(
            case=r.get("case"),
            visit=r.get("visit"),
            cohort=r.get("cohort", "control"),
            edge=r["edge"],
            control=r.get("control"),
            method=role,
            repeat=j,
            cpu_ms=timing["cpu_ms"],
            wall_ms=timing["wall_ms"],
            **{
                f"{stage}_{clock}_ns": (timing["breakdown"] or {}).get(f"{stage}_{clock}_ns")
                for stage in ("stock", "scout", "rescue")
                for clock in ("cpu", "wall")
            },
        )
        for r in (*valid, *controls)
        for role, parts in r["timings"].items()
        for j, timing in enumerate(parts, 1)
    ]
    by_arm = {
        mode: [item for item in all_times if item["method"] == mode and item["control"] is None]
        for mode in run.MODES
    }
    true_targets = {
        kind: dict(
            n=sum(row["target_count"] for row in group),
            by_method={
                mode: sum(brief(row)["physical_gates"][mode] for row in group) for mode in run.MODES
            },
        )
        for kind in ("miss", "matched")
        if (group := [row for row in valid if row.get("kind") == kind])
    }
    summary = dict(
        attempts=len(rows),
        valid=len(valid),
        lanes=len(lanes),
        excluded=[
            {k: row[k] for k in ("case", "visit", "status")}
            for row in rows
            if row["status"] != "processed"
        ],
        incremental_decisions=dict(Counter(detail["decision"] for detail in lanes)),
        incremental_extra_epochs=sum(len(lane["evaluated_epochs"]) for lane in lanes),
        full_extra_epochs=sum(h["active_epochs"] for row in valid for h in row["traces"]["full"]),
        coarse_cfo_bins=21,
        gate_counts={mode: sum(sum(r["gate_counts"][mode]) for r in valid) for mode in run.MODES},
        paired_added_gates={
            mode: sum(d["native_only"] for r in valid for d in r["gate_transitions"][mode])
            for mode in run.MODES
            if mode != "stock"
        },
        paired_lost_gates={
            mode: sum(d["production_only"] for r in valid for d in r["gate_transitions"][mode])
            for mode in run.MODES
            if mode != "stock"
        },
        physical_targets=true_targets,
        clocks={
            mode: {
                k: dict(distribution(v), within_20=sum(x <= 20 for x in v))
                for k in ("cpu_ms", "wall_ms")
                if (v := [x[k] for x in observed])
            }
            for mode, observed in by_arm.items()
        },
        paired_clock_delta_ms_incremental_minus_full={
            clock: distribution(
                [
                    a[clock] - b[clock]
                    for a, b in zip(by_arm["incremental"], by_arm["full"], strict=True)
                ]
            )
            for clock in ("wall_ms", "cpu_ms")
        },
        paired_clock_delta_ms_incremental_minus_stock={
            clock: distribution(
                [
                    a[clock] - b[clock]
                    for a, b in zip(by_arm["incremental"], by_arm["stock"], strict=True)
                ]
            )
            for clock in ("wall_ms", "cpu_ms")
        },
        controls={f"{r['edge']}:{r['control']}": brief(r) for r in controls},
        host_scope="Intel Core Ultra 9 285K, pinned separate x86 host cores 0/1, nice 10",
        position_attempted=False,
    )
    return summary, all_times, lanes


def bars(ax, title, labels, values, xmax, xlabel, fmt):
    plot.header(ax, title, xlabel, labels, xmax)
    for group, values_for_group in enumerate(values):
        for offset, value, color in zip(
            (-0.30, -0.10, 0.10, 0.30), values_for_group, COLORS, strict=True
        ):
            ax.barh(group + offset, value, height=0.16, color=color)
            ax.text(
                value + xmax * 0.013, group + offset, format(value, fmt), va="center", fontsize=8.5
            )


def render(summary, output):
    wall = summary["clocks"]["incremental"]["wall_ms"]
    positive = summary["incremental_decisions"]["stock_positive"]
    fig, (recovery, runtime) = plot.canvas(
        TITLE,
        f"{summary['valid']}/{summary['attempts']} saved dual-RX visits "
        "· 16 planted or negative controls · three timed repeats",
        f"All {positive} positive stock lanes retained their exact candidate arrays. "
        f"Incremental rescue finished within 20 ms on {wall['within_20']}/{wall['n']} "
        "real calls. The measurement ends at native candidate output.",
    )
    fig.texts[0].set_fontsize(23)
    fig.subplots_adjust(left=0.164, right=0.930, bottom=0.279, wspace=0.47)
    targets = summary["physical_targets"]
    bars(
        recovery,
        "Archived target detection",
        [f"{targets['miss']['n']} prior misses", f"{targets['matched']['n']} prior matches"],
        [[targets[k]["by_method"][m] for m in run.MODES] for k in ("miss", "matched")],
        10,
        "Gate-passing physical targets",
        "d",
    )
    stats = (("cpu_ms", "p50"), ("wall_ms", "p50"), ("wall_ms", "p95"))
    ms = [[summary["clocks"][m][clock][pct] for m in run.MODES] for clock, pct in stats]
    bars(
        runtime,
        "Complete matched detector calls",
        ("CPU p50", "Wall p50", "Wall p95"),
        ms,
        max(max(items) for items in ms) * 1.19,
        "Host milliseconds",
        ".2f",
    )
    runtime.axvline(20, color=plot.INK, linestyle=":", linewidth=0.9)
    fig.legend(
        handles=[
            plot.Patch(color=color, label=label)
            for color, label in zip(COLORS, LABELS, strict=True)
        ],
        loc="lower left",
        bbox_to_anchor=(0.052, 0.137),
        ncol=4,
        frameon=False,
        fontsize=10.5,
    )
    for ext in ("png", "pdf"):
        buffer = io.BytesIO()
        opts = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        fig.savefig(buffer, format=ext, facecolor="white", **opts)
        write(output / f"incremental-rescue.{ext}", buffer.getvalue())
    plot.plt.close(fig)


def publish(source, out):
    summary, timing, lanes = aggregate(*measured(source))
    save_json(out / "qualification.json", summary)
    csv_file(out / "timing.csv", timing)
    csv_file(out / "lanes.csv", lanes)
    render(summary, out)
    members = [
        "qualification.json",
        "timing.csv",
        "lanes.csv",
        "incremental-rescue.png",
        "incremental-rescue.pdf",
    ]
    if out == source:
        members += [
            "PROTOCOL.md",
            "release.json",
            "build-receipt.json",
            "abi-witness.json",
            "feature-gate.json",
            "source-lock.json.gz",
            "lower.json.gz",
            "upper.json.gz",
        ]
    save_json(
        out / "evidence-lock.json",
        dict(
            files={name: run._sha(out / name) for name in members},
            report_source_sha256=run._sha(Path(__file__)),
            position_attempted=False,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=run.REPORT, type=Path)
    parser.add_argument("--out", default=run.REPORT, type=local_output)
    args = parser.parse_args()
    publish(args.source, args.out)
