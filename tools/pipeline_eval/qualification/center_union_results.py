"""Publish the frozen regional nomination and exact detector comparison."""

import argparse
import io
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import distribution
from . import center_union_eval as run
from . import scout_stage_figures as plot
from .prefix_figures import csv_file

COLORS = (plot.BASE, plot.DIAGNOSTIC, plot.CANDIDATE)
LABELS = ("Stock wide", "Replace fourth region", "Union up to five regions")


def sum_pairs(items):
    return {key: sum(r[key] for r in items) for key in ("production_only", "native_only")}


def stats():
    lock = run.load(run.REPORT / "source-lock.json.gz")
    for name, digest in lock["inputs"].items():
        whole_iq.checked(ROOT / name, digest)
    runs, controls = [], {}
    for edge in ("lower", "upper"):
        document = run.load(run.REPORT / f"{edge}.json.gz")
        if document["edge"] != edge or document["lock_sha256"] != run._digest(encoded(lock)):
            raise ValueError("measured panel differs from its prospective sample lock")
        for expected, receipt in zip(
            (x for x in lock["capture"] if x["edge"] == edge), document["measured"], strict=True
        ):
            if any(receipt[k] != val for k, val in expected.items()):
                raise ValueError("measured capture does not match its selected input")
            runs.append(receipt)
        controls[edge] = {
            name: dict(
                positives={k: sum(v) for k, v in row["gate_counts"].items()},
                physical_targets={
                    k: sum(x["physical_passes"] for x in v)
                    for k, v in row["target_results"].items()
                },
                target_count=row["target_count"],
            )
            for name, row in document["controls"].items()
        }
    valid = [r for r in runs if r["status"] == "processed"]
    timing = [
        dict(case=r["case"], visit=r["visit"], cohort=r["cohort"], method=k, repeat=i, **t)
        for r in valid
        for k, v in r["timings"].items()
        for i, t in enumerate(v, 1)
    ]
    stock = [x for row in valid for x in row["traces"]["stock"]]
    union = [x for row in valid for x in row["traces"]["union"]["values"]]
    for row in valid:
        run.center_union_gate.preserved(row["traces"]["stock"], row["traces"]["union"]["values"])
    gates = {
        role: sum_pairs([v for r in valid for v in r["stock_gate_compared"][role]])
        for role in ("replace", "union")
    }
    hinted_pairs = []
    for row in valid:
        p = run.projections(row["payloads"])
        hinted_pairs.extend(
            run.compare_probes(a, b, run.RATE)
            for a, b in zip(p["replace"], p["union"], strict=True)
        )
    summary = dict(
        scheduled=len(runs),
        admitted=len(valid),
        excluded=[
            {k: r[k] for k in ("case", "visit", "status")}
            for r in runs
            if r["status"] != "processed"
        ],
        exact_null_stock=len(valid),
        peaks={
            "stock_pretop": sum(lane["stock_peaks"] for lane in stock),
            "stock_topk": sum(lane["retained_stock"] for lane in stock),
            "with_extra_support_lanes": sum(lane["added_epochs"] > 0 for lane in union),
            **{
                k: sum(lane[k] for lane in union)
                for k in (
                    "stock_peaks",
                    "extra_peaks",
                    "added_epochs",
                    "retained_stock",
                    "retained_extra",
                )
            },
        },
        positives={k: sum(sum(r["gate_counts"][k]) for r in valid) for k in run.MODES},
        gate_matches_against_stock=gates,
        union_gate_matches_against_replacement=sum_pairs(hinted_pairs),
        controls=controls,
        target_results={
            kind: dict(
                n=len(choose),
                by_mode={
                    mode: dict(
                        physical_gated=sum(
                            t["physical_passes"] for r in choose for t in r["target_results"][mode]
                        ),
                        alias_gated=sum(
                            t["passes"] for r in choose for t in r["target_results"][mode]
                        ),
                    )
                    for mode in run.MODES
                },
            )
            for kind in ("miss", "matched")
            if (choose := [r for r in valid if r.get("kind") == kind])
        },
        times={
            mode: {
                key: dict(**distribution(values), within_20ms=sum(x <= 20 for x in values))
                for key in ("cpu_ms", "wall_ms", "native_cpu_ms", "coarse_cpu_ms")
                if (values := [r[key] for r in timing if r["method"] == mode])
            }
            for mode in run.MODES
        },
        position_attempted=False,
    )
    return summary, timing


def horizontal(ax, title, xlabel, names, values, xmax, fmt):
    plot.header(ax, title, xlabel, names, xmax)
    for j, group in enumerate(values):
        for i, (value, color) in enumerate(zip(group, COLORS, strict=True)):
            index = j + (i - 1) * 0.23
            ax.barh(index, value, height=0.18, color=color)
            ax.text(value + xmax * 0.015, index, format(value, fmt), va="center", fontsize=9)


def render(summary, out):
    fig, (detection, time) = plot.canvas(
        "Preserve stock timing regions while adding a fifth hint",
        f"{summary['admitted']} authentic dual-RX visits · 3 rotating repeats · detector-only",
        f"The fifth region preserved all {summary['peaks']['stock_peaks']:,} pre-top-eight stock "
        f"peak keys. The shared top-eight kept {summary['peaks']['retained_extra']} novel slots. "
        "Physical target matching uses the unfolded CFO. Complete call timings include the FFTW "
        "scout for both hinted paths. Geometry is outside this measurement.",
    )
    fig.subplots_adjust(bottom=0.281)
    cases = summary["target_results"]
    labels = (
        f"Prior physical misses\n{cases['miss']['n']} targets",
        f"Prior matched\n{cases['matched']['n']} targets",
    )
    gains = [
        tuple(cases[k]["by_mode"][m]["physical_gated"] for m in run.MODES)
        for k in ("miss", "matched")
    ]
    horizontal(
        detection,
        "Archived target recovered",
        "Gate-passing physical targets",
        labels,
        gains,
        10,
        "d",
    )
    names = ("Complete CPU p50", "Complete wall p50", "Complete wall p95")
    vals = [
        tuple(summary["times"][m][key][q] for m in run.MODES)
        for key, q in (("cpu_ms", "p50"), ("wall_ms", "p50"), ("wall_ms", "p95"))
    ]
    horizontal(
        time,
        "Matched detector calls",
        "Host milliseconds",
        names,
        vals,
        max(max(values) for values in vals) * 1.18,
        ".2f",
    )
    time.axvline(20, color=plot.INK, linestyle=":", linewidth=0.9)
    fig.legend(
        handles=[plot.Patch(color=c, label=name) for c, name in zip(COLORS, LABELS, strict=True)],
        loc="lower left",
        bbox_to_anchor=(0.052, 0.148),
        ncol=3,
        frameon=False,
        fontsize=10.5,
    )
    for ext in ("png", "pdf"):
        buf = io.BytesIO()
        opts = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        fig.savefig(buf, format=ext, facecolor="white", **opts)
        write(out / f"center-union.{ext}", buf.getvalue())
    plot.plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=local_output, default=run.REPORT)
    out = p.parse_args().out
    summary, times = stats()
    save_json(out / "qualification.json", summary)
    csv_file(out / "timing.csv", times)
    render(summary, out)
    members = ["qualification.json", "timing.csv", "center-union.png", "center-union.pdf"]
    if out == run.REPORT:
        members += [
            "PROTOCOL.md",
            "build-receipt.json",
            "release.json",
            "feature-gate.json",
            "abi-witness.json",
            "source-lock.json.gz",
            "lower.json.gz",
            "upper.json.gz",
        ]
    save_json(
        out / "evidence-lock.json",
        dict(
            files={name: run._sha(out / name) for name in members},
            scorer_sha256=run._sha(Path(__file__)),
            position_attempted=False,
        ),
    )


if __name__ == "__main__":
    main()
