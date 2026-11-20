"""Export modeled queues and terminal real delivery-clock replay outcomes."""

import argparse
import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from .. import iq_service, whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import distribution
from . import arrival_queue as pace
from . import arrival_queue_cost as costs
from .arrival_clock import simulate
from .full_v5_check import _sha
from .prefix_figures import csv_file

INCREMENTAL_SHA = "a9d21f818840f19aaae1742627e65a2e519a7297187d77dff58b440ee5dff408"
METHOD = {"control": "Stock wide", "candidate": "Fifth center", "incremental": "Incremental"}
QUEUE_CASES = (0, 1, None)


def timing_ms(samples, name):
    values = distribution(float(x) / 1e6 for x in samples)
    return {f"{name}_{key}_ms": values[key] for key in ("p50", "p95", "p99", "max")}


def queues(events, ident, mode):
    actual = [
        (
            r["visit"],
            r["arrival_ns"],
            "detector" if r["status"] == "processed" else r["status"],
            r["detector_cpu_ns"],
            r["detector_wall_ns"],
        )
        for r in events
    ]
    source = {r["visit"]: r for r in events if r["status"] == "processed"}
    for wall in (False, True):
        for workers in (1, 2):
            unbounded = simulate(actual, workers, wall=wall)
            minimum = unbounded["max_waiting"]
            for capacity in QUEUE_CASES:
                queue = (
                    unbounded
                    if capacity is None
                    else simulate(actual, workers, capacity, wall=wall)
                )
                pooled = queue["completed"]
                admitted = {r[0] for r in pooled}
                dropped = [
                    dict(
                        visit=i,
                        sample_start=source[i]["sample_start"],
                        sample_end=source[i]["sample_end"],
                        arrival_ns=source[i]["arrival_ns"],
                    )
                    for i in source
                    if i not in admitted
                ]
                result = dict(
                    id=ident,
                    mode=mode,
                    clock="wall" if wall else "cpu",
                    workers=workers,
                    waiting_slots="unbounded" if capacity is None else capacity,
                    minimum_lossless_waiting=minimum,
                    max_waiting=queue["max_waiting"],
                    physical_slots=len(events),
                    valid_slots=len(source),
                    completed=len(pooled),
                    invalid_capture=len(events) - len(source),
                    dropped=len(dropped),
                    drain_ms=queue["drain_ns"] / 1e6,
                    delivery_span_s=actual[-1][1] / pace.NS,
                    offered_cpu_s=sum(r[3] for r in actual) / pace.NS,
                    offered_wall_s=sum(r[4] for r in actual) / pace.NS,
                    **timing_ms((r[2] - r[1] for r in pooled), "wait"),
                    **timing_ms((r[3] - r[1] for r in pooled), "age"),
                )
                yield result, dropped


def terminal(attempt, events):
    state = whole_iq.read(attempt / "service.json")
    whole_iq.checked(attempt / "service.log", state["log_sha256"])
    path = attempt / "visits.jsonl"
    rows = sorted(
        [json.loads(line) for line in path.read_bytes().splitlines()], key=lambda r: r["visit"]
    )
    finished = attempt / "end.json"
    witness = whole_iq.read(finished) if finished.is_file() else None
    complete = iq_service.succeeded(state) and witness is not None
    if witness:
        whole_iq.checked(path, witness["output_sha256"])
        if (
            witness["end"]["memory.max"] != whole_iq.MEMORY
            or witness["end"]["memory.swap.max"]
            or witness["end"]["memory.events.oom_kill"]
            or witness["end"]["cgroup"] != witness["start"]["cgroup"]
        ):
            raise ValueError("paced process left the declared memory and swap bounds")
    if len({r["visit"] for r in rows}) != len(rows) or (complete and len(rows) != len(events)):
        raise ValueError("actual paced trace lacks correct physical visit coverage")
    for r in rows:
        expected = events[r["visit"]]
        if any(r[k] != v for k, v in expected.items()) or r["released_ns"] < r["arrival_ns"]:
            raise ValueError("scheduled clock/counter/native binding changed during pacing")
        if r["outcome"] != "queue_drop" and not (
            r["arrival_ns"] <= r["released_ns"] <= r["started_ns"] <= r["emitted_ns"]
        ):
            raise ValueError("paced emission did not preserve chronological queue flow")
    return rows, witness, state, complete


def observed(rows, witness, ident, mode, complete, scheduled):
    counts = Counter(r["outcome"] for r in rows)
    live = [r for r in rows if r["outcome"] == "emitted"]
    clock = witness["end"] if witness else {}
    all_valid = [r for r in scheduled if r["status"] == "processed"]
    return dict(
        id=ident,
        mode=mode,
        status="complete" if complete else "failed_or_partial",
        physical_slots=len(scheduled),
        accounted_slots=len(rows),
        valid_slots=len(all_valid),
        native_packets_emitted=counts["emitted"],
        invalid_capture=counts["invalid_capture"],
        queue_drops=counts["queue_drop"],
        prefetch_late=sum(r["available_ns"] > r["arrival_ns"] for r in rows),
        native_packets_by_next_delivery=sum(
            r["visit"] + 1 < len(scheduled)
            and r["emitted_ns"] <= scheduled[r["visit"] + 1]["arrival_ns"]
            for r in live
        ),
        native_packets_with_next_delivery=sum(r["visit"] + 1 < len(scheduled) for r in live),
        capture_span_s=scheduled[-1]["arrival_ns"] / pace.NS,
        drain_ms=max(
            (max((r["emitted_ns"] for r in live), default=0) - scheduled[-1]["arrival_ns"]) / 1e6,
            0.0,
        )
        if complete
        else None,
        detector_cpu_s=sum(r["native_cpu_ns"] for r in live) / pace.NS,
        detector_wall_s=sum(r["native_wall_ns"] for r in live) / pace.NS,
        memory_peak_bytes=clock.get("memory.peak"),
        rss_peak_kib=clock.get("rss_peak_kib"),
        service_cpu_s=(clock["cpu.stat.usage_usec"] - witness["start"]["cpu.stat.usage_usec"]) / 1e6
        if witness
        else None,
        service_wall_s=clock["monotonic_s"] - witness["start"]["monotonic_s"] if witness else None,
        **timing_ms((r["emitted_ns"] - r["arrival_ns"] for r in live), "age"),
        **timing_ms((r["started_ns"] - r["released_ns"] for r in live), "wait"),
        **timing_ms((r["released_ns"] - r["arrival_ns"] for r in rows), "release_delay"),
        **timing_ms((r["native_wall_ns"] for r in live), "native_wall"),
        **timing_ms((r["native_cpu_ns"] for r in live), "native_cpu"),
    )


def model(work, report):
    lock = pace.plan(work, report)
    events = {
        (ident, mode): pace.readgz(whole_iq.checked(report / path["events"], path["sha256"]))
        for ident, spec in lock["cases"].items()
        for mode, path in spec["modes"].items()
    }
    extra, _ = costs.extra_events(INCREMENTAL_SHA, report)
    for ident, sequence in extra.items():
        stock = events[ident, "control"]
        paired = ("visit", "arrival_ns", "delivery_clock", "sample_start", "sample_end", "status")
        if any(any(a[f] != b[f] for f in paired) for a, b in zip(stock, sequence, strict=True)):
            raise ValueError("incremental timing did not use identical physical visits")
        events[ident, "incremental"] = sequence
    timelines, removed = [], []
    for (ident, mode), sequence in events.items():
        for row, drops in queues(sequence, ident, mode):
            timelines.append(row)
            if drops:
                removed.append(dict(**row, dropped_visits=drops))
    csv_file(report / "queue-model.csv", timelines)
    pace.writegz(report / "modeled-drops.json.gz", removed)
    return events, timelines


def finish_plot(report, summary, models, measured, match):
    colors = {"control": "#176f70", "candidate": "#b94e38", "incremental": "#4f5890"}
    fig, grid = plt.subplots(2, 2, figsize=(14, 8.6))
    fig.suptitle(
        "Packets arrive about every 43 ms on these recordings",
        x=0.06,
        ha="left",
        fontsize=21,
        fontweight="bold",
        color="#19303a",
    )
    model_ax, actual_ax, age_ax, costs_ax = grid.flat
    ordered = [(case, mode) for case in pace.CPUS for mode in METHOD]
    ticks = [f"{case[-4:]}\n{METHOD[mode]}" for case, mode in ordered]
    winners = {
        (r["id"], r["mode"], r["clock"], r["waiting_slots"]): r for r in models if r["workers"] == 1
    }
    for k, (ident, mode) in enumerate(ordered):
        for i, name in enumerate(("cpu", "wall")):
            val = winners[ident, mode, name, 1]["dropped"]
            model_ax.bar(
                k + (-0.15 if i == 0 else 0.15),
                val,
                0.26,
                color=colors[mode],
                alpha=0.42 if i == 0 else 1,
            )
            if val:
                model_ax.text(
                    k + (-0.15 if i == 0 else 0.15),
                    val,
                    str(val),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
    model_ax.set_xticks(range(len(ordered)), ticks, fontsize=8)
    model_ax.set_title("Modeled drops, one worker and one waiting slot")
    model_ax.set_ylabel("Dropped physical visits")
    model_ax.text(
        0.02,
        0.97,
        "Pale = archived CPU, solid = archived wall",
        transform=model_ax.transAxes,
        va="top",
        fontsize=8,
    )
    for k, row in enumerate(summary):
        height = row["queue_drops"]
        actual_ax.bar(k, height, 0.60, color=colors[row["mode"]])
        actual_ax.text(k, height, str(height), ha="center", va="bottom")
        actual_ax.set_xticks(
            range(len(summary)),
            [f"{r['id'][-4:]}\n{METHOD[r['mode']]}" for r in summary],
            fontsize=8,
        )
        live = sorted(
            (r["emitted_ns"] - r["arrival_ns"]) / 1e6
            for r in measured
            if r["id"] == row["id"] and r["mode"] == row["mode"] and r["outcome"] == "emitted"
        )
        if live:
            age_ax.plot(
                live,
                [(i + 1) / len(live) * 100 for i in range(len(live))],
                color=colors[row["mode"]],
                ls="-" if row["id"].startswith("DS26") else "--",
                label=f"{row['id'][-4:]} {METHOD[row['mode']]}",
            )
    actual_ax.set_title("Measured drops in complete paced replay")
    actual_ax.set_ylabel("Dropped physical visits")
    age_ax.axvline(20, color="#708b94", ls=":", linewidth=1)
    age_ax.set_xscale("log")
    age_ax.set_xlabel("Scheduled delivery → verified packet emission (ms)")
    age_ax.set_ylabel("Percent of emitted packets")
    age_ax.set_title("Actual packet age under one waiting slot")
    age_ax.legend(fontsize=8, loc="lower right")
    for i, (ident, mode) in enumerate(ordered):
        m = next(r for r in match if r["id"] == ident and r["mode"] == mode)
        median, p95 = m["cpu_p50_ms"], m["cpu_p95_ms"]
        costs_ax.bar(i, median, 0.54, color=colors[mode])
        costs_ax.plot([i, i], [median, p95], color="#202f35", linewidth=1.6)
    costs_ax.set_xticks(range(len(ordered)), ticks, fontsize=8)
    costs_ax.set_title("Same-core midpoint detector CPU · median and p95")
    costs_ax.set_ylabel("Single native call (ms)")
    for ax in grid.flat:
        ax.grid(axis="y", alpha=0.22)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(rect=(0, 0.02, 1, 0.94), h_pad=3)
    for suffix in ("png", "pdf"):
        fig.savefig(report / f"queue-evidence.{suffix}", dpi=145)
    plt.close(fig)


def publish(work, report):
    events, models = model(work, report)
    measured, summary, files = [], [], []
    for ident in pace.CPUS:
        for mode in pace.MODES:
            attempt = work / ident / mode
            rows, witness, state, complete = terminal(attempt, events[ident, mode])
            for name, data in (("service.json", state), ("worker-bounds.json", witness)):
                filename = f"{ident}-{mode}-{name}"
                save_json(report / filename, data)
                files.append(filename)
            filename = f"{ident}-{mode}-service.log"
            write(report / filename, (attempt / "service.log").read_bytes())
            files.append(filename)
            measured.extend(dict(r, id=ident, mode=mode) for r in rows)
            summary.append(observed(rows, witness, ident, mode, complete, events[ident, mode]))
    csv_file(report / "paced-replay.csv", summary)
    pace.writegz(report / "paced-events.json.gz", measured)
    drops = [
        dict(
            id=r["id"],
            mode=r["mode"],
            visit=r["visit"],
            sample_start=r["sample_start"],
            sample_end=r["sample_end"],
            scheduled_arrival_ns=r["arrival_ns"],
            released_ns=r["released_ns"],
        )
        for r in measured
        if r["outcome"] == "queue_drop"
    ]
    if drops:
        csv_file(report / "observed-drops.csv", drops)
        files.append("observed-drops.csv")
    preferred = pace.readgz(report / "same-core-visits.json.gz")
    compared = []
    for ident in pace.CPUS:
        for mode in METHOD:
            rows = [r for r in preferred if r["id"] == ident and r["mode"] == mode]
            if len(rows) != costs.WIDTH:
                raise ValueError(
                    "same-core native comparison did not traverse its locked midpoint block"
                )
            valid = [r for r in rows if r["status"] == "processed"]
            compared.append(
                dict(
                    id=ident,
                    mode=mode,
                    cpu=rows[0]["cpu"],
                    visits=len(rows),
                    measured_calls=len(valid),
                    **timing_ms((r["detector_cpu_ns"] for r in valid), "cpu"),
                    **timing_ms((r["detector_wall_ns"] for r in valid), "wall"),
                )
            )
    csv_file(report / "same-core-summary.csv", compared)
    finish_plot(report, summary, models, measured, compared)
    files.extend(
        [p.name for p in report.glob("*-events.json.gz") if not p.name.startswith("paced")]
    )
    files.extend(
        (
            "source-lock.json",
            "PROTOCOL.md",
            "queue-model.csv",
            "modeled-drops.json.gz",
            "paced-replay.csv",
            "paced-events.json.gz",
            "same-core-lock.json",
            "same-core-summary.csv",
            "same-core-visits.json.gz",
            "queue-evidence.png",
            "queue-evidence.pdf",
        )
    )
    save_json(
        report / "stage-lock.json",
        dict(
            cases=list(pace.CPUS),
            files={name: _sha(report / name) for name in files},
            incremental_prediction_lock_sha256=INCREMENTAL_SHA,
            renderer_sha256=_sha(Path(__file__)),
        ),
    )
    completed = sum(r["status"] == "complete" for r in summary)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="paced-native-arrival-queue",
            title="Native detector queues at capture delivery cadence",
            boundary="Paced saved IQ through native packets, with separate queue models",
            sample=f"DS26-0197 and DS29-0316 · {completed}/4 complete paced runs",
            note="One live detector and one waiting slot. Packet age excludes position fitting.",
            seal="stage-lock.json",
            image="queue-evidence.png",
            pdf="queue-evidence.pdf",
            csv="paced-replay.csv",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=pace.REPORT)
    parser.add_argument("--model-only", action="store_true")
    args = parser.parse_args()
    (model if args.model_only else publish)(args.work, args.out)
