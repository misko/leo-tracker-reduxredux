"""Present genuine complete-output timing, paced age, and position evidence."""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km, distribution
from . import arrival_queue as queue
from . import dual_lane_build as build
from . import dual_lane_pace as pace
from . import screening_figures
from .arrival_queue_position import METHODS as SERIAL_POSITION_METHODS
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

NAMES = {
    "typed-serial": "Serial dual",
    "split-serial": "Split serial",
    "split-parallel": "Parallel lanes",
}
COLOR = {"typed-serial": "#965442", "split-serial": "#7a80a1", "split-parallel": "#137979"}
MODES = ("stock", "fifth")


def sealed(path, expected=None):
    if expected:
        whole_iq.checked(path, expected)
    proof = whole_iq.read(path)
    for name, digest in proof["files"].items():
        whole_iq.checked(path.parent / name, digest)
    return proof


def stats(rows, mode, role, ident="all"):
    selected = [
        r
        for r in rows
        if (r["mode"], r["role"]) == (mode, role) and (ident == "all" or r["id"] == ident)
    ]
    profile = dict(
        recording=ident,
        mode=mode,
        role=role,
        calls=len(selected),
        decoded_within_20ms=sum(r["wall_ns"] <= 20_000_000 for r in selected),
        typed_within_20ms=sum(r["typed_ns"] <= 20_000_000 for r in selected),
    )
    for field in ("wall_ns", "typed_ns", "cpu_ns"):
        sample = distribution(r[field] / 1e6 for r in selected)
        profile.update(
            {f"{field.removesuffix('_ns')}_{k}_ms": sample[k] for k in ("p50", "p95", "p99", "max")}
        )
    for lane in (0, 1):
        sample = distribution(r["lanes"][lane]["cpu_ns"] / 1e6 for r in selected if r["lanes"])
        profile.update({f"lane{lane}_cpu_{k}_ms": sample[k] for k in ("p50", "p95")})
    return profile


def standard_axes(fig, axes):
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.23)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93), h_pad=2.4)


def timing_plot(report, rows, summary):
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8))
    fig.suptitle(
        "Parallel antenna processing shortens complete detector response",
        x=0.055,
        ha="left",
        fontsize=19,
        fontweight="bold",
        color="#17313b",
    )
    for idx, mode in enumerate(MODES):
        ax = axes[0, idx]
        for role in NAMES:
            group = sorted(
                r["wall_ns"] / 1e6 for r in rows if (r["mode"], r["role"]) == (mode, role)
            )
            ax.step(
                group,
                [(i + 1) * 100 / len(group) for i in range(len(group))],
                color=COLOR[role],
                where="post",
                label=NAMES[role],
                linewidth=1.9,
            )
        ax.axvline(20, color="#54656d", ls="--", linewidth=1, label="20 ms response target")
        ax.set(
            title="Stock wide" if mode == "stock" else "Unconditional fifth center",
            xscale="log",
            xlabel="Dual CI16 to both decoded rows (ms)",
            ylabel="Percent of calls",
        )
    axes[0, 0].legend(frameon=False, fontsize=8, loc="lower right")
    cpu = axes[1, 0]
    compliance = axes[1, 1]
    labels = []
    for k, row in enumerate(x for x in summary if x["recording"] == "all"):
        color = COLOR[row["role"]]
        labels.append(f"{row['mode'].capitalize()}\n{NAMES[row['role']]}")
        cpu.bar(k, row["cpu_p50_ms"], width=0.58, color=color)
        cpu.plot([k, k], [row["cpu_p50_ms"], row["cpu_p95_ms"]], color="#19303a", linewidth=1.5)
        value = row["decoded_within_20ms"]
        compliance.bar(k, value, width=0.58, color=color)
        compliance.annotate(
            f"{value}/{row['calls']}",
            (k, value),
            textcoords="offset points",
            xytext=(0, 3),
            ha="center",
            fontsize=8,
        )
    cpu.set(title="Total process CPU · median and p95", ylabel="CPU time (ms)")
    compliance.set(title="Both decoded rows within 20 ms", ylabel="Measured calls")
    for ax in axes[1]:
        ax.set_xticks(range(len(labels)), labels, fontsize=8)
    standard_axes(fig, axes)
    for suffix in ("png", "pdf"):
        fig.savefig(report / f"dual-lane.{suffix}", dpi=145)
    plt.close(fig)


def native_report(report):
    proof = report / "native-lock.json"
    sealed(proof)
    data = queue.readgz(report / "native-measurements.json.gz")
    rows = data["rows"]
    summary = [
        stats(rows, mode, role, ident)
        for ident in ("all", "DS26-0197", "DS29-0316")
        for mode in MODES
        for role in NAMES
    ]
    flat = []
    for m in rows:
        record = {k: v for k, v in m.items() if k not in ("lanes", "glrt_lanes_cpu_ns")}
        for lane in (0, 1):
            data_lane = m["lanes"][lane] if m["lanes"] else {}
            record.update(
                {f"lane{lane}_{k}": data_lane.get(k) for k in ("cpu", "hint", "cpu_ns", "wall_ns")}
            )
            record[f"serial_glrt_lane{lane}_cpu_ns"] = (
                m["glrt_lanes_cpu_ns"][lane] if "glrt_lanes_cpu_ns" in m else None
            )
        flat.append(record)
    csv_file(report / "native-timing.csv", flat)
    csv_file(report / "native-summary.csv", summary)
    timing_plot(report, rows, summary)
    names = (
        "native-lock.json",
        "native-timing.csv",
        "native-summary.csv",
        "dual-lane.png",
        "dual-lane.pdf",
    )
    save_json(
        report / "stage-lock.json",
        dict(
            cases=["DS26-0197", "DS29-0316"],
            files={name: _sha(report / name) for name in names},
            renderer_sha256=_sha(Path(__file__)),
        ),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="dual-lane-native",
            title="Complete native detector on parallel antenna lanes",
            boundary="Authenticated dual CI16 through complete ordered native rows",
            sample="Two recordings · 128 actual windows · three matched execution roles",
            note="Wall includes both decoded rows. Archive reads and position are separate.",
            seal="stage-lock.json",
            image="dual-lane.png",
            pdf="dual-lane.pdf",
            csv="native-timing.csv",
        ),
    )


def paced_figure(report, stage_rows):
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.9), squeeze=False)
    fig.suptitle(
        "Complete fifth-center packets at recorded arrival cadence",
        x=0.06,
        ha="left",
        fontsize=17,
        fontweight="bold",
        color="#17313b",
    )
    fields = ("native_wall_p50_ms", "age_p50_ms", "age_p95_ms", "age_max_ms")
    short = ("Detector wall\nmedian", "Packet age\nmedian", "Packet age\np95", "Packet age\nmax")
    for i, row in enumerate(stage_rows):
        label = row["execution"]
        color = ("#a35645", "#137979")[i]
        shift = (-0.16, 0.16)[i]
        for j, field in enumerate(fields):
            if row[field] is not None:
                axes[0, 0].bar(
                    j + shift, float(row[field]), 0.28, color=color, label=label if j == 0 else None
                )
        emitted, dropped = int(row["native_packets_emitted"]), int(row["queue_drops"])
        before = int(row["native_packets_by_next_delivery"])
        later = emitted - before
        # The last emitted packet has no next scheduled delivery. Keep it in the
        # remainder so that the plotted physical visit accounting stays exact.
        axes[0, 1].barh(i, before, color="#137979")
        axes[0, 1].barh(i, later, left=before, color="#7b9ba0")
        axes[0, 1].barh(i, dropped, left=emitted, color="#a35645")
    axes[0, 0].set(title="Complete packet clocks", ylabel="Elapsed time (ms)")
    axes[0, 0].set_xticks(range(len(short)), short, fontsize=8)
    axes[0, 0].legend(frameon=False, fontsize=8)
    axes[0, 1].set(title="Valid physical visits", xlabel="Physical visits")
    axes[0, 1].set_yticks((0, 1), [r["execution"] for r in stage_rows], fontsize=8)
    axes[0, 1].text(
        0.01,
        0.97,
        "Teal: before next delivery · grey: later/last · red: drop",
        transform=axes[0, 1].transAxes,
        va="top",
        fontsize=8,
    )
    standard_axes(fig, axes)
    for suffix in ("png", "pdf"):
        fig.savefig(report / f"paced-dual-lane.{suffix}", dpi=145)
    plt.close(fig)


def paced_report(report):
    proof = report / "paced-lock.json"
    sealed(proof)
    prior = queue.REPORT / "stage-lock.json"
    previous_stage = sealed(prior, pace.MEASURED_PARENT)
    data = whole_iq.checked(
        queue.REPORT / "paced-replay.csv", previous_stage["files"]["paced-replay.csv"]
    )
    (older,) = [
        r
        for r in csv.DictReader(data.read_text().splitlines())
        if (r["id"], r["mode"]) == (pace.CASE, pace.MODE)
    ]
    current = whole_iq.read(report / "paced-summary.json")
    stage_rows = [
        dict(older, execution="Historical serial fifth"),
        dict(current, execution="Parallel fifth"),
    ]
    csv_file(report / "paced-comparison.csv", stage_rows)
    paced_figure(report, stage_rows)
    files = (proof.name, "paced-comparison.csv", "paced-dual-lane.png", "paced-dual-lane.pdf")
    save_json(
        report / "stage-lock.json",
        dict(
            cases=[pace.CASE],
            files={n: _sha(report / n) for n in files},
            previous_stage_sha256=pace.MEASURED_PARENT,
        ),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="dual-lane-paced",
            title="Two-antenna fifth center at recorded delivery cadence",
            boundary="Complete 300 s saved IQ through one-slot paced native output",
            sample="One recorded waveform · new parallel execution and historic serial control",
            note="Native packet age excludes the separate geographic solver.",
            seal="stage-lock.json",
            image="paced-dual-lane.png",
            pdf="paced-dual-lane.pdf",
            csv="paced-comparison.csv",
        ),
    )
    if not (report / "positions-candidate-lock.json").is_file():
        return
    positions(report)


def positions(report):
    pred = report / "positions-candidate-lock.json"
    sealed(pred)
    earlier = queue.REPORT / "position-score-lock.json"
    sealed(earlier)
    (actual,) = rows_from(report / "positions-candidate.jsonl.gz")
    prior = {
        r["method"]: r
        for r in rows_from(queue.REPORT / "matched-positions.jsonl.gz")
        if r["id"] == pace.CASE
    }
    names = (pace.METHOD, SERIAL_POSITION_METHODS[pace.MODE], queue.whole_center_union.METHOD)
    matches = [actual, *(prior[m] for m in names[1:])]
    bindings = ("paired_paced_native_sha256", "catalog_sha256", "original_request_sha256", "tile")
    if any(any(r[k] != actual[k] for k in bindings) for r in matches):
        raise ValueError("matched geographic predictions did not share input authority")
    _, (ref,) = held_references(None, [pace.CASE])
    rows = []
    for record in matches:
        for arm in ARMS:
            result = record["result"]
            value = result["arms"][arm]
            rows.append(
                dict(
                    id=record["id"],
                    arm=arm,
                    method=record["method"],
                    origin=record["origin"],
                    status=result["status"],
                    drops=record["dropped"],
                    position_error_km=distance_km(ref["truth"], value["latlon"]),
                    rf_rms_hz=value.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    position_wall_s=record["resources"].get("wall_s"),
                )
            )
    csv_file(report / "position-scores.csv", rows)
    pack(report / "matched-positions.jsonl.gz", matches)
    seal = "position-score-lock.json"
    files = ("position-scores.csv", "matched-positions.jsonl.gz", pred.name, "stage-lock.json")
    save_json(
        report / seal,
        dict(
            cases=[pace.CASE],
            files={n: _sha(report / n) for n in files},
            prior_position_sha256=_sha(earlier),
        ),
    )
    series = []
    for key, label, method in zip(
        ("one", "stock", "all_visits"),
        (
            "Parallel retained packets",
            "Historical serial retained packets",
            "All valid archived packets",
        ),
        names,
        strict=True,
    ):
        item = dict(
            key=key,
            label=label,
            value=method,
            file="matched-positions.jsonl.gz",
            native_field="paired_capture_sha256",
        )
        if key != "one":
            item["match"] = list(bindings)
        series.append(item)
    chart = dict(
        id="dual-lane-paced-position",
        method=pace.METHOD,
        scope="roof",
        cases="sealed",
        seal=seal,
        title="Position from two-antenna fifth center at recorded cadence",
        caption=(
            "Same saved DS29 waveform, native search and causal offer. Both paced paths "
            "use their own verified admitted packets. Original v5 uses capture-era inputs."
        ),
        provenance=["position-scores.csv", pred.name, "stage-lock.json"],
        series=series,
    )
    save_json(report / "figures.json", dict(version=2, charts=[chart]))
    screening_figures.generate(report / "position-charts", evidence=report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("native", "paced"))
    parser.add_argument("--out", type=local_output)
    args = parser.parse_args()
    if args.action == "native":
        native_report(args.out or build.REPORT)
    else:
        paced_report(args.out or pace.REPORT / "paced")
