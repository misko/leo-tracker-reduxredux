"""Summarize and publish the matched three-lag native detector witness."""

import argparse
import gzip
import io
import json
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import distribution
from . import multilag_search_eval as run
from . import scout_stage_figures as plot
from .prefix_figures import csv_file

TITLE = "Three-lag Qin pilot timing before the native fifth center"
LABELS = ("Four centers", "Released fifth center", "Three-lag fifth center")
COLORS = (plot.BASE, "#2B6591", plot.CANDIDATE)


def aggregation(source):
    plan = source / "source-lock.json"
    lock = whole_iq.read(plan)
    for path, digest in lock["files"].items():
        whole_iq.checked(ROOT / path, digest)
    report = json.loads(gzip.decompress((source / "waveform.json.gz").read_bytes()))
    if report["lock_sha256"] != run._sha(plan):
        raise ValueError("measured raw receipts use a different prospective source lock")
    real, synthetic = [], []
    for row in report["rows"]:
        (synthetic if row["cohort"] == "synthetic" else real).append(row)
    keys = ("case", "segment", "visit", "rx", "edge", "cohort", "kind", "iq_sha256")
    if sorted(tuple(r[k] for k in keys) for r in real) != sorted(
        tuple(r[k] for k in keys) for r in lock["windows"]
    ):
        raise ValueError("detector receipts changed the prospective authentic roster")
    complete = [row for row in real if row["status"] == "processed"]
    timing = [
        dict(
            case=r.get("case"),
            visit=r.get("visit"),
            cohort=r["cohort"],
            kind=r["kind"],
            edge=r["edge"],
            method=role,
            repeat=j,
            **clock,
        )
        for r in (*complete, *synthetic)
        for role, samples in r["time"].items()
        for j, clock in enumerate(samples, 1)
    ]
    target_results = {}
    for cohort in ("primary", "held"):
        for kind in ("miss", "retained", "negative"):
            group = [r for r in complete if (r["cohort"], r["kind"]) == (cohort, kind)]
            target_results[f"{cohort}:{kind}"] = dict(
                n=len(group),
                **{
                    role: dict(
                        physical=sum(
                            v["category"] == "physical_gated"
                            for r in group
                            for v in r["matches"].get(role, [])
                        ),
                        actual_winner=sum(
                            v["actual_winner_matches"]
                            for r in group
                            for v in r["matches"].get(role, [])
                        ),
                        alias_gate=sum(
                            v["any_alias_gate"] for r in group for v in r["matches"].get(role, [])
                        ),
                        gates=sum(sum(r["flags"][role]) for r in group),
                    )
                    for role in run.MODES
                },
            )
    times = {
        m: [t for t in timing if t["cohort"] != "synthetic" and t["method"] == m] for m in run.MODES
    }
    publication = dict(
        scheduled=len(real),
        completed=len(complete),
        physical=target_results,
        unavailable=[
            {k: r[k] for k in ("case", "visit", "status", "detail")}
            for r in real
            if r["status"] != "processed"
        ],
        held_eligibility={k: r["availability"] for k, r in lock["held"].items()},
        gates={m: sum(sum(r["flags"][m]) for r in complete) for m in run.MODES},
        differences={
            m: {
                k: sum(c[k] for r in complete for c in r["compared"][m])
                for k in ("production_only", "native_only")
            }
            for m in ("four", "five")
        },
        stock_peaks_preserved=sum(
            trace["stock_peaks"] for row in complete for trace in row["trace"]["multilag"]["lanes"]
        ),
        changed_requested_hints=sum(
            a != b
            for row in complete
            for a, b in zip(
                row["trace"]["five"]["hints"], row["trace"]["multilag"]["hints"], strict=True
            )
        ),
        admitted_regions={
            m: sum(t["added_epochs"] > 0 for row in complete for t in row["trace"][m]["lanes"])
            for m in ("five", "multilag")
        },
        controls={
            f"{r['edge']}:{r['kind']}": dict(
                gates={m: sum(x) for m, x in r["flags"].items()},
                physical={
                    m: sum(v["category"] == "physical_gated" for v in g)
                    for m, g in r["matches"].items()
                },
            )
            for r in synthetic
        },
        recovered=[
            dict(
                case=r["case"],
                visit=r["visit"],
                rx=r["rx"],
                cohort=r["cohort"],
                **r["matches"]["multilag"][0],
            )
            for r in complete
            if r["kind"] == "miss" and r["matches"]["multilag"][0]["category"] == "physical_gated"
        ],
        timing={
            m: {
                k: dict(distribution(v), at_most_20ms=sum(x <= 20 for x in v))
                for k in ("cpu_ms", "wall_ms", "scout_cpu_ms")
                if (v := [r[k] for r in rows])
            }
            for m, rows in times.items()
        },
        paired_multilag_minus_five_ms={
            k: distribution(
                [a[k] - b[k] for a, b in zip(times["multilag"], times["five"], strict=True)]
            )
            for k in ("wall_ms", "cpu_ms", "scout_cpu_ms")
        },
        build=lock["multilag"],
        cpus=report["affinity"],
        position_attempted=False,
    )
    return publication, timing


def bars(axis, title, units, labels, rows):
    xmax = max(max(group) for group in rows) * 1.26
    plot.header(axis, title, units, labels, xmax)
    for i, group in enumerate(rows):
        for j, (value, color) in enumerate(zip(group, COLORS, strict=True)):
            at = i + (j - 1) * 0.22
            axis.barh(at, value, height=0.17, color=color)
            axis.text(value + 0.017 * xmax, at, f"{value:.3g}", va="center", fontsize=9)


def plot_summary(summary, output):
    score = summary["physical"]
    clock = summary["timing"]["multilag"]["wall_ms"]
    figure, (quality, runtime) = plot.canvas(
        TITLE,
        f"{summary['completed']}/{summary['scheduled']} saved dual-receiver visits "
        "· 12 synthetic controls · warm x86 host",
        f"The three-lag scout preserved all {summary['stock_peaks_preserved']:,} original "
        f"coarse peak keys before the common top eight. {clock['at_most_20ms']}/{clock['n']} "
        "complete raw calls met 20 ms wall. This stage ends at native hypotheses.",
    )
    figure.subplots_adjust(left=0.171, right=0.925, bottom=0.277, wspace=0.44)
    groups = ("primary:miss", "held:miss", "primary:retained", "held:retained")
    bars(
        quality,
        "Original physical pilots recovered",
        "Gate-passing targets",
        ("9 primary misses", "6 held misses", "2 primary positives", "2 held positives"),
        [[score[k][m]["physical"] for m in run.MODES] for k in groups],
    )
    clocks = (("cpu_ms", "p50"), ("wall_ms", "p50"), ("wall_ms", "p95"))
    bars(
        runtime,
        "Complete dual-receiver detector",
        "Host milliseconds",
        ("CPU p50", "Wall p50", "Wall p95"),
        [[summary["timing"][m][k][p] for m in run.MODES] for k, p in clocks],
    )
    runtime.axvline(20, color=plot.INK, linestyle=":", linewidth=0.9)
    figure.legend(
        handles=[plot.Patch(color=c, label=label) for c, label in zip(COLORS, LABELS, strict=True)],
        loc="lower left",
        bbox_to_anchor=(0.052, 0.139),
        ncol=3,
        frameon=False,
        fontsize=10,
    )
    for ext in ("png", "pdf"):
        buffer = io.BytesIO()
        opts = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        figure.savefig(buffer, format=ext, facecolor="white", **opts)
        write(output / f"multilag-search.{ext}", buffer.getvalue())
    plot.plt.close(figure)


def publish(source, out):
    summary, times = aggregation(source)
    save_json(out / "qualification.json", summary)
    csv_file(out / "timing.csv", times)
    plot_summary(summary, out)
    files = ["qualification.json", "timing.csv", "multilag-search.png", "multilag-search.pdf"]
    if source == out:
        files.extend(("PROTOCOL.md", "source-lock.json", "waveform.json.gz"))
    save_json(
        out / "evidence-lock.json",
        dict(
            files={n: run._sha(out / n) for n in files},
            reporter_sha256=run._sha(Path(__file__)),
            position_attempted=False,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default=run.REPORT, type=Path)
    p.add_argument("--out", default=run.REPORT, type=local_output)
    args = p.parse_args()
    publish(args.source, args.out)
