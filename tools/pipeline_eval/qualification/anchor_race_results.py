"""Aggregate the prospectively locked full-anchor comparison and detector chart."""

import argparse
import gzip
import io
import json
from pathlib import Path

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import distribution
from . import anchor_race_eval as run
from . import scout_stage_figures as plot
from .prefix_figures import csv_file

ROLES = ("capture", "mean", "race", "sham", "wide")
PROPOSALS = ("race", "mean", "sham")
LABELS = ("Installed capture", "Same-support mean", "Anchor race", "Rotated sham", "Wide stock")
COLORS = (plot.BASE, "#97734A", plot.CANDIDATE, "#706697", "#2A6998")
TITLE = "Complete-anchor panels before exact capture refinement"


def measured(root):
    lock = json.loads((root / "source-lock.json").read_bytes())
    for path, value in lock["sources"].items():
        source = Path(path)
        if run._sha(source) != value:
            raise ValueError(f"acquisition source no longer matches the freeze: {source.name}")
    rows, controls, producers = [], [], {}
    for case, frozen in lock["roster"].items():
        report = json.loads(gzip.decompress((root / f"{case}.json.gz").read_bytes()))
        if report["id"] != case or report["locked_sha256"] != run.parent._digest(encoded(lock)):
            raise ValueError("run metadata differs from the original source lock")
        producers[case] = {
            k: report[k]
            for k in ("edge", "archive_sha256", "provenance", "affinity", "peak_rss_kib")
        }
        for expected, result in zip(frozen, report["rows"], strict=True):
            if any(expected[key] != result[key] for key in expected):
                raise ValueError(f"{case} waveform binding differs from the locked visit")
            if result["status"] == "processed" and len(result["pairs"]) != 2:
                raise ValueError("warm genuine visit lacks its paired repeats")
            rows.append(dict(result, case=case, edge=report["edge"]))
        controls.extend(
            dict(x, control=name, case=case, edge=report["edge"])
            for name, x in report["controls"].items()
        )
    return rows, controls, producers


def gate_counts(rows, mode):
    counts = [p for row in rows for p in row["positives"][mode]]
    return dict(
        capture_positive=sum(p["production_positive"] for p in counts),
        positive=sum(p["native_positive"] for p in counts),
        matched=sum(len(p["positive_matches"]) for p in counts),
        missing=sum(p["production_only"] for p in counts),
        additional=sum(p["native_only"] for p in counts),
    )


def rank_counts(rows, mode):
    traces = [p for row in rows for p in row["pairs"][0]["coarse"][mode]]
    return dict(
        original_keys=sum(len(p["exact_ranks"]) for p in traces),
        retained_keys=sum(rank is not None for p in traces for rank in p["exact_ranks"]),
        original_keys_in_scored_interiors=sum(sum(p["eligible"]) for p in traces),
        same_ordered_rank=sum(
            pos == rank for p in traces for pos, rank in enumerate(p["exact_ranks"], 1)
        ),
        original_top1_in_top8=sum(bool(p["exact_ranks"] and p["exact_ranks"][0]) for p in traces),
        original_top1_still_top1=sum(
            bool(p["exact_ranks"] and p["exact_ranks"][0] == 1) for p in traces
        ),
        first_pass_receiver_lanes=len(traces),
    )


def physical_counts(rows):
    return {
        role: dict(
            physical=sum(p["physical_passes"] for row in rows for p in row["physical"][role]),
            alias_allowed=sum(p["passes"] for row in rows for p in row["physical"][role]),
            total=sum(len(row["physical"][role]) for row in rows),
        )
        for role in ROLES
    }


def aggregate(rows, synthetic, producer):
    true = [row for row in rows if row["status"] == "processed"]
    pairs = [
        dict(
            case=row["case"],
            visit=row.get("visit"),
            edge=row["edge"],
            control=row.get("control"),
            kind=row.get("kind", "comparison"),
            method=role,
            repeat=repeat,
            cpu_ms=data["cpu_ms"],
            wall_ms=data["wall_ms"],
            acquires=len(data["acquisitions"]),
            **{
                f"{clock}_ms": sum(q.get(f"{clock}_ms", 0.0) for q in data["acquisitions"])
                for clock in ("proposal_cpu", "nomination_cpu", "rescore_cpu")
            },
            held=bool(row.get("held")),
        )
        for row in (*true, *synthetic)
        for repeat, call in enumerate(row["pairs"], 1)
        for role, data in call["modes"].items()
    ]
    clocks = {
        role: [p for p in pairs if p["method"] == role and p["control"] is None] for role in ROLES
    }
    work = {
        role: [
            q for row in true for call in row["pairs"] for q in call["modes"][role]["acquisitions"]
        ]
        for role in PROPOSALS
    }
    return dict(
        attempts=len(rows),
        complete=len(true),
        excluded=[
            {k: row[k] for k in ("case", "visit", "status")}
            for row in rows
            if row["status"] != "processed"
        ],
        gates={role: gate_counts(true, role) for role in ROLES},
        old_panel_gates={
            role: gate_counts([r for r in true if not r.get("held")], role) for role in ROLES
        },
        original_coarse={role: rank_counts(true, role) for role in PROPOSALS},
        original_coarse_prior_panel={
            role: rank_counts([r for r in true if not r.get("held")], role) for role in PROPOSALS
        },
        original_coarse_held={
            role: rank_counts([r for r in true if r.get("held")], role) for role in PROPOSALS
        },
        physical={
            key: physical_counts([r for r in true if r.get("kind") == key])
            for key in ("miss", "matched")
        },
        clocks={
            role: {
                key: dict(distribution(values), within_20=sum(t <= 20 for t in values))
                for key in (
                    "cpu_ms",
                    "wall_ms",
                    "proposal_cpu_ms",
                    "nomination_cpu_ms",
                    "rescore_cpu_ms",
                )
                if (values := [r[key] for r in clock])
            }
            for role, clock in clocks.items()
        },
        work={
            role: dict(
                acquires=len(calls),
                **{
                    key: sum(q[key] for q in calls)
                    for key in (
                        "original_cells",
                        "proposal_cells",
                        "rescored_cells",
                        "proposal_anchor_frame_terms",
                        "original_anchor_frame_terms",
                        "nominations",
                    )
                },
                bit_exact_rescored=sum(
                    call["exact_rescored"][role] for row in true for call in row["pairs"]
                ),
            )
            for role, calls in work.items()
        },
        race_after_coarse_cpu_ms=distribution(
            [
                race["cpu_ms"]
                - race["stage_cpu_ms"].get("coarse_grid", 0.0)
                - race["stage_cpu_ms"].get("final_peak_select", 0.0)
                for row in true
                for call in row["pairs"]
                if (race := call["modes"]["race"])
            ]
        ),
        race_paired_cpu_ratio_to_capture=distribution(
            [
                call["modes"]["race"]["cpu_ms"] / call["modes"]["capture"]["cpu_ms"]
                for row in true
                for call in row["pairs"]
            ]
        ),
        controls={
            f"{r['edge']}:{r['control']}": dict(
                gates={role: gate_counts([r], role) for role in ROLES},
                physical=physical_counts([r]),
            )
            for r in synthetic
        },
        provenance=producer,
        score_boundary="detector only",
    ), pairs


def bars(ax, title, names, values, axis, fmt):
    xmax = max(max(row) for row in values) * 1.23
    plot.header(ax, title, axis, names, xmax)
    for i, row in enumerate(values):
        for j, (value, color) in enumerate(zip(row, COLORS, strict=True)):
            at = i + (j - 2) * 0.15
            ax.barh(at, value, height=0.12, color=color)
            ax.text(value + xmax * 0.012, at, format(value, fmt), va="center", fontsize=8.7)


def render(summary, out):
    race = summary["original_coarse"]["race"]
    stage = summary["clocks"]["race"]["wall_ms"]
    figure, (gate, runtime) = plot.canvas(
        TITLE,
        f"{summary['complete']}/{summary['attempts']} saved dual-RX visits "
        "· both pilot edges · 10 controls",
        f"The race kept {race['retained_keys']}/{race['original_keys']} original coarse keys. "
        f"Exact rescoring precedes the original refinement. {stage['within_20']}/{stage['n']} "
        "race calls finished within 20 ms wall. This chart ends at native detector output.",
    )
    figure.subplots_adjust(left=0.16, right=0.934, bottom=0.278, wspace=0.44)
    bars(
        gate,
        "Original candidates and physical targets",
        ("48 original gates", "4 held prior misses", "2 held prior matches"),
        [
            [summary["gates"][m]["matched"] for m in ROLES],
            [summary["physical"]["miss"][m]["physical"] for m in ROLES],
            [summary["physical"]["matched"][m]["physical"] for m in ROLES],
        ],
        "Matched or recovered gates",
        "d",
    )
    stat = (("cpu_ms", "p50"), ("wall_ms", "p95"))
    bars(
        runtime,
        "Complete matched detector calls",
        ("CPU p50", "Wall p95"),
        [[summary["clocks"][m][key][q] for m in ROLES] for key, q in stat],
        "Host milliseconds",
        ".1f",
    )
    runtime.axvline(20, color=plot.INK, linestyle=":", linewidth=0.9)
    figure.legend(
        handles=[plot.Patch(color=c, label=m) for c, m in zip(COLORS, LABELS, strict=True)],
        loc="lower left",
        bbox_to_anchor=(0.053, 0.144),
        ncol=5,
        frameon=False,
        fontsize=10,
    )
    for ext in ("png", "pdf"):
        buffer = io.BytesIO()
        opts = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        figure.savefig(buffer, format=ext, facecolor="white", **opts)
        write(out / f"anchor-race.{ext}", buffer.getvalue())
    plot.plt.close(figure)


def publish(source, out):
    summary, times = aggregate(*measured(source))
    save_json(out / "qualification.json", summary)
    csv_file(out / "timing.csv", times)
    render(summary, out)
    names = ("qualification.json", "timing.csv", "anchor-race.png", "anchor-race.pdf")
    targets = [out / name for name in names]
    if source == out:
        targets.extend(
            source / name
            for name in (
                "PROTOCOL.md",
                "source-lock.json",
                *[f"{case}.json.gz" for case in run.parent.CASES],
            )
        )
    save_json(
        out / "evidence-lock.json",
        dict(
            files={f.name: run._sha(f) for f in targets},
            scorer_sha256=run._sha(Path(__file__)),
            position_attempted=False,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=run.REPORT)
    p.add_argument("--out", type=local_output, default=run.REPORT)
    args = p.parse_args()
    publish(args.source, args.out)
