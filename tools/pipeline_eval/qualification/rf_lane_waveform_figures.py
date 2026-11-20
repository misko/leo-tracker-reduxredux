"""Render observed routing dispositions and separately charged waveform costs."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from .arrival_queue import NS
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .rf_lane_waveform import REPORT

NAME = "rf-lane-stage"
ROLES = ("wide", "original")
LABELS = {"wide": "Wide four-region", "original": "Row-wise original"}
COLORS = {"wide": "#167373", "original": "#5367a3"}


def measurements(report):
    manifest = whole_iq.read(report / "manifest.json")
    control = manifest["legacy_clock_control"]
    previous = whole_iq.read(whole_iq.checked(Path(control["manifest"]), control["sha256"]))
    detector, source = [], []
    for ident, case in manifest["cases"].items():
        duration = case["last_arrival_ns"] / NS
        for role in ROLES:
            summary = case["branches"][role]["summary"]
            historic = previous["cases"][ident]["branches"][role]["summary"]
            detector.append(
                dict(
                    recording=ident,
                    stage="detector",
                    detector=role,
                    recorded_span_s=duration,
                    original_rf_hz=case["selected_rf_hz"],
                    worker_core=case["cpus"][role],
                    assigned=summary["assigned_visits"],
                    unassigned=summary["counts"].get("unassigned", 0),
                    invalid=case["invalid_visits"],
                    by_close=summary["observed_by_cutoff"],
                    busy=summary["counts"].get("dropped_busy", 0),
                    drain=summary["late_drain_packets"],
                    positive_by_close=summary["positive_by_cutoff"],
                    positive_within_20ms_by_close=summary["positive_within_20ms"],
                    worker_cpu_s=summary["worker_cpu_ns"] / NS,
                    native_cpu_s=summary["detector_cpu_ns"] / NS,
                    startup_cpu_s=summary["startup_cpu_ns"] / NS,
                    peak_cgroup_bytes=summary["peak_cgroup_memory_bytes"],
                    historical_worker_cpu_s=historic["worker_cpu_ns"] / NS,
                )
            )
        name = case["stage"]
        stage = whole_iq.read(whole_iq.checked(report / name, manifest["files"][name]))
        source.append(
            dict(
                recording=ident,
                stage="source",
                recorded_span_s=duration,
                publisher_core=case["cpus"]["publisher"],
                decode_readback_wall_s=stage["stage_start_to_ready_ns"] / NS,
                decode_readback_cpu_s=stage["stage_decode_and_readback_cpu_us"] / 1_000_000,
                compressed_capture_bytes=stage["stage"]["compressed_bytes"],
                staged_iq_bytes=stage["stage"]["bytes"],
                peak_cgroup_bytes=stage["stage"]["end"]["memory.peak"],
                staging_cpu_during_replay_us=stage["stage_cpu_during_replay_us"],
                publisher_replay_cpu_s=stage["publisher_replay_cpu_ns"] / NS,
            )
        )
    return detector, source


def draw(report, detector, source):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import PercentFormatter

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ((queue, cpu), (prep, size)) = plt.subplots(2, 2, figsize=(11.6, 7.5))
    fig.subplots_adjust(left=0.24, right=0.94, top=0.84, bottom=0.14, wspace=0.35, hspace=0.83)
    fig.suptitle("One physical RF assigned to original GLRT", y=0.967, fontsize=17, weight="bold")
    fig.text(
        0.5, 0.923, "Full recorded-clock replays  ·  one waiting visit per detector", ha="center"
    )
    labels = [f"{r['recording']}  {LABELS[r['detector']]}" for r in detector]
    outcomes = (
        ("by_close", "Completed by close", "#167373"),
        ("busy", "Busy drop", "#ba7258"),
        ("drain", "Drained after close", "#daa632"),
    )
    for i, row in enumerate(detector):
        previous = 0
        for field, _, color in outcomes:
            share = row[field] / row["assigned"]
            queue.barh(i, share, left=previous, color=color, height=0.53)
            previous += share
        queue.text(
            0.02, i, f"{row['by_close']:,} / {row['assigned']:,}", va="center", color="white"
        )
        for field, offset, color in (
            ("worker_cpu_s", -0.15, COLORS[row["detector"]]),
            ("historical_worker_cpu_s", 0.15, "#bcc7d1"),
        ):
            value = row[field]
            cpu.barh(i + offset, value, color=color, height=0.27)
            cpu.text(value + 2, i + offset, f"{value:.1f}", va="center", fontsize=8)
    queue.set(yticks=range(len(detector)), yticklabels=labels, xlim=(0, 1), title="Queue outcomes")
    queue.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    queue.set_xlabel("Share of visits assigned to worker")
    cpu.set(yticks=[], title="Worker process CPU", xlabel="CPU seconds")
    cpu.set_ylim(queue.get_ylim())
    cpu.set_xlim(
        0, 1.13 * max(max(r["worker_cpu_s"], r["historical_worker_cpu_s"]) for r in detector)
    )
    queue.legend(
        handles=[Patch(color=color, label=label) for _, label, color in outcomes],
        loc="lower left",
        bbox_to_anchor=(0, -0.42),
        ncol=3,
        fontsize=8,
        frameon=False,
    )
    cpu.legend(
        handles=[
            Patch(color=color, label=label)
            for color, label in (
                ("#167373", "RF-routed wide"),
                ("#5367a3", "RF-routed original"),
                ("#bcc7d1", "Historical clock control"),
            )
        ],
        loc="lower left",
        bbox_to_anchor=(0, -0.42),
        ncol=2,
        fontsize=8,
        frameon=False,
    )
    for i, row in enumerate(source):
        for key, offset, color in (
            ("decode_readback_wall_s", -0.15, "#5367a3"),
            ("decode_readback_cpu_s", 0.15, "#bcc7d1"),
        ):
            value = row[key]
            prep.barh(i + offset, value, color=color, height=0.28)
            prep.text(value + 0.6, i + offset, f"{value:.1f}", va="center", fontsize=8)
        for key, offset, color in (
            ("staged_iq_bytes", -0.15, "#5367a3"),
            ("compressed_capture_bytes", 0.15, "#bcc7d1"),
        ):
            gb = row[key] / 1_000_000_000
            size.barh(i + offset, gb, color=color, height=0.28)
            size.text(gb + 0.10, i + offset, f"{gb:.2f}", va="center", fontsize=8)
    names = [r["recording"] for r in source]
    prep.set(
        yticks=range(len(source)),
        yticklabels=names,
        title="Source decode and readback",
        xlabel="Seconds",
        xlim=(0, 1.14 * max(r["decode_readback_wall_s"] for r in source)),
    )
    size.set(yticks=[], title="Separate source allocation", xlabel="Bytes (GB)", xlim=(0, 12.5))
    for ax in (queue, cpu, prep, size):
        ax.invert_yaxis()
        ax.grid(axis="x", color="#e2e8f0")
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    fig.text(
        0.05,
        0.058,
        "Source panels  ·  wall and CPU seconds  |  staged CI16 and compressed reads",
        color="#475569",
        fontsize=9,
    )
    fig.text(
        0.05,
        0.03,
        "Historical timing uses different cores and the installed original peak selector.",
        color="#475569",
        fontsize=9,
    )
    fig.savefig(report / f"{NAME}.png", dpi=180)
    fig.savefig(report / f"{NAME}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def generate(report):
    detector, source = measurements(report)
    draw(report, detector, source)
    rows = detector + source
    fields = dict.fromkeys(key for row in rows for key in row)
    csv_file(report / "stage-timing.csv", [fields | row for row in rows])
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id=NAME,
            title="Exclusive physical RF routing at recorded pace",
            sample="Two complete 300-second recordings",
            boundary="Two pinned detectors and one independent waiting slot each",
            note="Busy drops and drain are measured against the assigned visit denominator. "
            "Historical CPU is descriptive because the selector and core allocation differ.",
            image=f"{NAME}.png",
            pdf=f"{NAME}.pdf",
            csv="stage-timing.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = (f"{NAME}.png", f"{NAME}.pdf", "stage-timing.csv", "stage-figure.json", "manifest.json")
    save_json(
        report / "stage-figure-lock.json", dict(files={name: _sha(report / name) for name in names})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    generate(parser.parse_args().report)
