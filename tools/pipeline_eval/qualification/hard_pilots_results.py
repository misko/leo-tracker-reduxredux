"""Seal the native-factor census and matched representative-time waveform witness."""

import argparse
import gzip
import io
import json
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import distribution
from . import hard_pilots_eval as run
from . import scout_stage_figures as plot
from .prefix_figures import csv_file

TITLE = "Pilot winners missed by both deployed timing budgets"
MODES = ("four", "five", "halves")
LABELS = ("Four native centers", "Released fifth center", "Representative-half fifth")
COLORS = (plot.BASE, "#2B6591", plot.CANDIDATE)


def measured(source):
    plan = source / "source-lock.json"
    parent = whole_iq.read(plan)
    for path, digest in parent["source_sha256"].items():
        whole_iq.checked(ROOT / path, digest)
    reception = json.loads(gzip.decompress((source / "waveform.json.gz").read_bytes()))
    if reception["source_sha256"] != run._sha(plan):
        raise ValueError("waveform evidence differs from its prospective source lock")
    for case in parent["cases"].values():
        for receipt in case["sources"].values():
            if "receipt" in receipt:
                whole_iq.checked(ROOT / receipt["receipt"], receipt["receipt_sha256"])
    targets = {
        (ident, r["visit"]): r for ident, item in parent["cases"].items() for r in item["selected"]
    }
    rows = {(r["id"], r["selection"]["visit"]): r for r in reception["rows"]}
    if (
        len(rows) != len(reception["rows"])
        or set(rows) != set(targets)
        or any(rows[k]["selection"] != targets[k] for k in rows)
    ):
        raise ValueError("waveform replay changed the scheduled target support")
    return parent["cases"], reception


def aggregate(cases, replay):
    rows = replay["rows"]
    admitted = [row for row in rows if row["status"] == "processed"]
    timings = [
        dict(
            recording=r["id"],
            visit=r["selection"]["visit"],
            edge=r["selection"]["edge"],
            group=r["group"],
            role=role,
            repeat=i,
            **time,
        )
        for r in admitted
        for role, data in r["times"].items()
        for i, time in enumerate(data, 1)
    ]
    census = {ident: r["counts"] for ident, r in cases.items()}
    hard = Counter()
    for ident in run.HARD:
        hard.update(census[ident])
    physical = {
        group: dict(
            scheduled=sum(r["group"] == group for r in rows),
            replayed=sum(r["group"] == group for r in admitted),
            matched={
                role: sum(
                    r["matched"][role]["category"] == "physical_gated"
                    for r in admitted
                    if r["group"] == group
                )
                for role in MODES
            },
            actual_winner={
                role: sum(
                    r["matched"][role]["actual_winner_matches"]
                    for r in admitted
                    if r["group"] == group
                )
                for role in MODES
            },
        )
        for group in ("hard", "control")
    }
    present_in_regions = Counter()
    for row in admitted:
        if row["group"] != "hard":
            continue
        selected = row["selection"]
        target, rx = selected["target"]["integer_epoch_sample"], selected["rx"]
        full, halves = (row["hints"][role]["trace"][rx] for role in ("five", "halves"))
        for role, centers in (
            ("four", full["ordinary"]),
            ("five", full["selected"]),
            ("halves", halves["selected"]),
        ):
            present_in_regions[role] += any(abs(c - target) <= 1 for c in centers)
    dataset = dict(
        census=census,
        all_hard_winners=dict(hard),
        physical=physical,
        selected_hard_integer_epoch_inside_coarse_region=dict(present_in_regions),
        excluded=[
            dict(id=r["id"], visit=r["selection"]["visit"], reason=r["reason"])
            for r in rows
            if r["status"] != "processed"
        ],
        gates={
            role: sum(
                sum(p[run.GATE] for p in rx["candidates"])
                for r in admitted
                for rx in r["candidates"][role]
            )
            for role in MODES
        },
        change_from_full_fifth={
            f"{side}_only": sum(
                c[f"{side}_only"] for r in admitted for c in r["gate_delta"]["five"]
            )
            for side in ("production", "native")
        },
        changed_half_hints=sum(
            a != b
            for r in admitted
            for a, b in zip(
                r["hints"]["five"]["centers"], r["hints"]["halves"]["centers"], strict=True
            )
        ),
        synthetic={
            f"{r['edge']}:{r['control']}": dict(
                gates={role: sum(v) for role, v in r["counts"].items()},
                physical_targets={
                    role: sum(x["category"] == "physical_gated" for x in v)
                    for role, v in r["target"].items()
                },
            )
            for r in replay["controls"]
        },
        timing={
            role: {
                key: dict(distribution(v), at_or_below_20ms=sum(x <= 20 for x in v))
                for key in ("wall_ms", "cpu_ms")
                if (v := [t[key] for t in timings if t["role"] == role])
            }
            for role in MODES
        },
        completed_calls=len(admitted),
        acquisition_affinity=replay["affinity"],
        position_attempted=False,
    )
    return dataset, timings


def plots(summary, out):
    overall, physical = summary["all_hard_winners"], summary["physical"]
    wall = summary["timing"]["halves"]["wall_ms"]["p50"]
    count = summary["completed_calls"]
    figure, (audit, real) = plot.canvas(
        TITLE,
        f"Six hard recordings · two held controls · {count} measured dual-RX CI16 windows",
        f"Across the six hard recordings, both deployed timing budgets missed "
        f"{overall['missing_both']:,}/{overall['winners']:,} original signed-CFO winners. "
        f"Two sample-half scouts plus native refinement took {wall:.2f} ms median host wall. "
        "The measurements stop at native candidates.",
    )
    figure.subplots_adjust(left=0.145, right=0.936, bottom=0.284, wspace=0.55)
    limit = (
        max(
            summary["census"][i]["missing_both"] / summary["census"][i]["winners"] for i in run.HARD
        )
        * 125
    )
    plot.header(
        audit, "Complete original winner census", "Missed by both policies (%)", run.HARD, limit
    )
    for index, ident in enumerate(run.HARD):
        row = summary["census"][ident]
        miss = row["missing_both"] / row["winners"] * 100
        absent = row["both_phases_absent"] / row["winners"] * 100
        audit.barh(index, miss, color="#D4AF8C", height=0.5)
        audit.barh(index, absent, color="#AD6A31", height=0.5)
        audit.text(miss + 0.018 * limit, index, f"{miss:.1f}%", va="center", fontsize=8.7)
    real_groups = ("hard", "control")
    max_n = max(physical[k]["replayed"] for k in real_groups)
    plot.header(
        real,
        "Authenticated waveform replay",
        "Original physical target gates",
        (
            f"Both missed · {physical['hard']['replayed']}",
            f"Held matches · {physical['control']['replayed']}",
        ),
        max_n + 1,
    )
    for j, k in enumerate(real_groups):
        for slot, (label, color) in enumerate(zip(MODES, COLORS, strict=True)):
            n = physical[k]["matched"][label]
            y = j + (slot - 1) * 0.23
            real.barh(y, n, color=color, height=0.18)
            real.text(n + 0.12, y, str(n), va="center", fontsize=8.7)
    figure.legend(
        handles=[
            plot.Patch(color="#AD6A31", label="No phase candidate in either budget"),
            *[
                plot.Patch(color=color, label=name)
                for color, name in zip(COLORS, LABELS, strict=True)
            ],
        ],
        loc="lower left",
        bbox_to_anchor=(0.054, 0.134),
        frameon=False,
        ncol=4,
        fontsize=9.2,
    )
    for ext in ("png", "pdf"):
        buffer = io.BytesIO()
        opts = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        figure.savefig(buffer, format=ext, facecolor="white", **opts)
        write(out / f"hard-pilots.{ext}", buffer.getvalue())
    plot.plt.close(figure)


def publish(source, out):
    summary, timing = aggregate(*measured(source))
    save_json(out / "qualification.json", summary)
    csv_file(out / "timing.csv", timing)
    csv_file(
        out / "winner-census.csv",
        [
            dict(recording=ident, metric=metric, count=value)
            for ident, row in summary["census"].items()
            for metric, value in row.items()
        ],
    )
    plots(summary, out)
    files = [
        "qualification.json",
        "timing.csv",
        "winner-census.csv",
        "hard-pilots.png",
        "hard-pilots.pdf",
    ]
    if source == out:
        files.extend(("PROTOCOL.md", "source-lock.json", "waveform.json.gz"))
    save_json(
        out / "evidence-lock.json",
        dict(
            files={n: run._sha(out / n) for n in files},
            publisher_sha256=run._sha(Path(__file__)),
            position_attempted=False,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=run.REPORT)
    p.add_argument("--out", type=local_output, default=run.REPORT)
    args = p.parse_args()
    publish(args.source, args.out)
