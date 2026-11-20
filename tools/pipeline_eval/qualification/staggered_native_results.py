"""Seal the paired RF measurements and render the three native branches."""

import argparse
import csv
import gzip
import shutil
from collections import Counter
from pathlib import Path

import matplotlib

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from . import staggered_native_build as build
from . import staggered_native_eval as evaluate
from .full_v5_check import _sha
from .native_hotpath_results import distribution

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

DISPLAY = {"four": "Four on both", "five": "Five on both", "mixed": "Staggered fifth"}


def table(path, rows):
    with path.open("w", newline="") as stream:
        out = csv.DictWriter(stream, fieldnames=list(rows[0]))
        out.writeheader()
        out.writerows(rows)


def exact_hashes(row):
    chosen = row["fixture"]["fifth_lane"]
    parts = row["payload_sha256"]
    return parts["mixed"] == [
        parts["five"][i] if i == chosen else parts["four"][i] for i in range(2)
    ]


def publish(work):
    report = build.REPORT
    locked = report / "source-lock.json"
    authority = whole_iq.read(locked)
    measurement = whole_iq.read(work / "measurements.json")
    if measurement["source_lock_sha256"] != _sha(locked):
        raise ValueError("measured native input differs from the published source lock")
    timings, science, selection = [], [], {}
    controls = []
    for case, observed in measurement["cases"].items():
        lock = authority["recorded"][case]
        valid = [r for r in lock if r["status"] == "valid"]
        if [r["fixture"] for r in observed["rows"]] != valid:
            raise ValueError("held timing omits a valid scheduled waveform")
        controls.extend(observed["controls"])
        extent = Counter((r["center_hz"], r["fifth_lane"]) for r in valid)
        selection[case] = dict(
            scheduled=len(lock),
            valid=len(valid),
            invalid=len(lock) - len(valid),
            centers={
                center: [extent[center, i] for i in range(2)]
                for center in sorted({r["center_hz"] for r in valid})
            },
            worker_peak_rss_kib=observed["peak_rss_kib"],
        )
        for row in observed["rows"]:
            capture = row["fixture"]
            if not exact_hashes(row) or len(row["timing"]) != 3:
                raise ValueError("mixed science or warm repetition changed")
            chosen = capture["fifth_lane"]
            if row["hints"]["mixed"][1 - chosen] != -1:
                raise ValueError("the stock lane ran the fifth proposal")
            for role in evaluate.ROLES:
                science.append(
                    dict(
                        case=case,
                        fixture=capture["name"],
                        role=role,
                        fifth_lane=chosen if role == "mixed" else None,
                        center_hz=capture["center_hz"],
                        lanes_with_scout={"four": 0, "five": 2, "mixed": 1}[role],
                        candidates_rx0=row["counts"][role][0],
                        candidates_rx1=row["counts"][role][1],
                        gates_rx0=row["gated"][role][0],
                        gates_rx1=row["gated"][role][1],
                        hint_rx0=row["hints"][role][0],
                        hint_rx1=row["hints"][role][1],
                        rx0_sha256=row["payload_sha256"][role][0],
                        rx1_sha256=row["payload_sha256"][role][1],
                    )
                )
            for repeat, logged in enumerate(row["timing"]):
                for order, role in enumerate(logged["order"]):
                    tick = logged["metrics"][role]
                    timings.append(
                        dict(
                            case=case,
                            fixture=capture["name"],
                            role=role,
                            fifth_lane=chosen if role == "mixed" else None,
                            center_hz=capture["center_hz"],
                            repeat=repeat,
                            order=order,
                            wall_ms=tick["wall_ns"] / 1e6,
                            cpu_ms=tick["cpu_ns"] / 1e6,
                            typed_wall_ms=tick["typed_ns"] / 1e6,
                            lane0_cpu_ms=tick["lanes"][0]["cpu_ns"] / 1e6,
                            lane1_cpu_ms=tick["lanes"][1]["cpu_ns"] / 1e6,
                            within_20ms=tick["wall_ns"] <= 20_000_000,
                        )
                    )
    summary, pairs = {}, {}
    for scope in ("all", *evaluate.CASES):
        rows = [r for r in timings if scope == "all" or r["case"] == scope]
        cells = summary[scope] = {}
        for role in evaluate.ROLES:
            local = [r for r in rows if r["role"] == role]
            numeric = [
                r for r in science if (scope == "all" or r["case"] == scope) and r["role"] == role
            ]
            cells[role] = dict(
                native_calls=len(local),
                within_20ms=sum(r["within_20ms"] for r in local),
                candidates=sum(r[f"candidates_rx{i}"] for r in numeric for i in range(2)),
                gates=sum(r[f"gates_rx{i}"] for r in numeric for i in range(2)),
                **{
                    k: distribution([r[k] for r in local])
                    for k in ("wall_ms", "cpu_ms", "typed_wall_ms")
                },
            )
        joined = {(r["fixture"], r["repeat"], r["role"]): r for r in rows}
        mixed = [r for r in rows if r["role"] == "mixed"]
        pairs[scope] = {
            side: {
                k: distribution([m[k] - joined[m["fixture"], m["repeat"], side][k] for m in mixed])
                for k in ("cpu_ms", "wall_ms")
            }
            for side in ("four", "five")
        }
    table(report / "stage.csv", timings)
    table(report / "branch-parity.csv", science)
    save_json(
        report / "summary.json",
        dict(timing=summary, paired=pairs, selection=selection, controls=controls),
    )
    write(report / "measurements.json.gz", gzip.compress(encoded(measurement), mtime=0))
    shutil.copyfile(work / "build/build.json", report / "build.json")
    plot(report, summary["all"])
    files = (
        "source-lock.json",
        "build.json",
        "summary.json",
        "stage.csv",
        "branch-parity.csv",
        "measurements.json.gz",
        "stage.png",
        "stage.pdf",
    )
    save_json(
        report / "result-lock.json",
        dict(files={n: _sha(report / n) for n in files}, publisher_sha256=_sha(Path(__file__))),
    )


def plot(report, data):
    fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.5))
    colors = ("#566f86", "#ad8556", "#107d73")
    for axis, metric, label in zip(
        axes,
        ("wall_ms", "cpu_ms"),
        ("Complete call wall (ms)", "Both threads' CPU (ms)"),
        strict=True,
    ):
        p50 = [data[k][metric]["p50"] for k in evaluate.ROLES]
        p95 = [data[k][metric]["p95"] for k in evaluate.ROLES]
        axis.bar(range(3), p50, width=0.52, color=colors)
        axis.scatter(range(3), p95, marker="D", color=colors, edgecolor="white", zorder=3)
        for i, y in enumerate(p50):
            axis.text(i, 0.7, f"{y:.2f}", ha="center", color="white", fontweight="bold", fontsize=9)
        axis.set_xticks(range(3), [DISPLAY[k] for k in evaluate.ROLES])
        axis.set_ylabel(label)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.18)
    axes[0].axhline(20, linestyle="--", color="#777777", linewidth=0.8)
    fig.text(0.06, 0.95, "One fifth-center search per dual visit", fontsize=16, fontweight="bold")
    fig.text(
        0.06,
        0.89,
        "96 held dual-RX windows and 288 warm calls per branch. Diamonds show p95.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.08, right=0.97, top=0.82, bottom=0.14, wspace=0.26)
    fig.savefig(report / "stage.png", dpi=170)
    fig.savefig(report / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
