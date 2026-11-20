"""Certify complete native inputs, refit actual drops, and compare both buffer sizes."""

import argparse
import csv
import gzip
import json
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import arrival_queue as pace
from . import arrival_queue_position as position
from . import arrival_queue_results as queue
from . import buffered_arrival_replay as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

METHODS = {"control": "buffered_arrival_stock", "candidate": "buffered_arrival_fifth"}
PAGE_IDS = {"control": "buffered-position-stock", "candidate": "buffered-position-fifth"}
FULL = {"control": pace.whole_center_union.BASELINE, "candidate": pace.whole_center_union.METHOD}


def archive(report, mode, ident):
    source = whole_iq.read(report / "source-lock.json")
    lock = whole_iq.read(
        whole_iq.checked(pace.PARENT / "prediction-lock.json", source["parent_prediction_sha256"])
    )

    def checked(name):
        return whole_iq.checked(pace.PARENT / name, lock["files"][name])

    rows = rows_from(checked("positions.jsonl.gz"))
    (baseline,) = [r for r in rows if r["id"] == ident and r["method"] == FULL[mode]]
    blob = gzip.decompress(checked(f"native/{mode}/{ident}.json.gz").read_bytes())
    if sha256(blob).hexdigest() != baseline["native_sha256"]:
        raise ValueError("archived measured position does not bind the exact complete native SHA")
    return baseline, json.loads(blob)


def support(rows, events, document):
    """Check closed raw outcomes and their exact ordered physical receiver support."""
    if len(rows) != len(events):
        raise ValueError("incomplete actual visit roster")
    probes = document["source"]["probes"]
    emitted, drops = set(), []
    for row, event in zip(rows, events, strict=True):
        if (row["visit"], row["full_visit_sha256"], row["sample_start"], row["sample_end"]) != (
            event["visit"],
            event["full_visit_sha256"],
            event["sample_start"],
            event["sample_end"],
        ):
            raise ValueError("paced raw envelope is unbound to its physical visit")
        valid = event["status"] == "processed"
        if valid and row["outcome"] == "emitted":
            emitted.add(row["visit"])
        elif valid and row["outcome"] == "queue_drop":
            drops.append(row["visit"])
        elif valid or row["outcome"] != "invalid_capture":
            raise ValueError("unknown/drop disposition does not match capture validity")
    emitted_pairs = [
        (p["visit_index"], p["receiver_id"]) for p in probes if p["visit_index"] in emitted
    ]
    if emitted_pairs != [(i, rx) for i in sorted(emitted) for rx in (0, 1)]:
        raise ValueError("replayed visits lack their original ordered dual receiver packets")
    if len(probes) != len(emitted_pairs) + 2 * len(drops):
        raise ValueError("dropped visits do not partition the complete input")
    return drops, len(emitted_pairs), pace.fingerprint(emitted_pairs)


def encounter(work, report, mode, ident, spec):
    declared = spec["modes"][mode]
    expected = pace.readgz(whole_iq.checked(report / declared["events"], declared["sha256"]))
    path = work / ident / mode
    if not (path / "visits.jsonl").is_file():
        service = whole_iq.read(path / "service.json")
        whole_iq.checked(path / "service.log", service["log_sha256"])
        return [], None, service, False, expected
    rows, witness, service, complete = queue.terminal(path, expected)
    if witness and not witness.get("exact_iq_manifest"):
        raise ValueError("paced worker has no complete IQ authority")
    if path.is_dir() and (path / "plan.json").exists():
        plan = whole_iq.read(path / "plan.json")
        if plan["events_sha256"] != declared["sha256"] or plan["mode"] != mode:
            raise ValueError("paced launch used another recording schedule")
    return rows, witness, service, complete, expected


def refit(work, report, mode):
    lock = pace.plan(work, report)
    witnesses, terminal = {}, {}
    for ident, spec in lock["cases"].items():
        rows, witness, service, complete, expected = encounter(work, report, mode, ident, spec)
        terminal[ident] = rows, witness, service, complete
        if not complete:
            witnesses[ident] = dict(status="incomplete paced trace", native_sha256=None)
            continue
        old, document = archive(report, mode, ident)
        drops, count, order = support(rows, expected, document)
        witnesses[ident] = dict(
            status="complete matched native input" if not drops else "genuine queue losses",
            archived_native_sha256=old["native_sha256"],
            exact_reused_native_sha256=old["native_sha256"] if not drops else None,
            emitted_native_rows=count,
            dropped_visits=drops,
            physical_pair_order_sha256=order,
            trace_sha256=witness["output_sha256"],
            original_request_sha256=old["original_request_sha256"],
        )
    name = f"position-{mode}-byte-bindings.json"
    save_json(report / name, dict(cases=witnesses, producer_sha256=_sha(Path(__file__))))
    with patch.multiple(
        position, METHODS=METHODS, terminal=lambda path, _: terminal[path.parent.name]
    ):
        position.run(work, report, mode)


def prior_member(name):
    receipt = whole_iq.read(whole_iq.checked(trial.BASE / "stage-lock.json", trial.BASE_STAGE))
    return whole_iq.checked(trial.BASE / name, receipt["files"][name])


def compare_drops(historical, current):
    old = {(r["id"], r["mode"], r["visit"]): r for r in historical if r["outcome"] == "queue_drop"}
    new = {(r["id"], r["mode"], r["visit"]): r for r in current if r["outcome"] == "queue_drop"}
    result = []
    for key in sorted(old.keys() | new.keys()):
        row = new.get(key) or old[key]
        if key in old and key in new and old[key]["sample_start"] != new[key]["sample_start"]:
            raise ValueError("same queue drop must name the same hardware counter")
        result.append(
            dict(
                **{
                    k: row[k]
                    for k in ("id", "mode", "visit", "sample_start", "sample_end", "arrival_ns")
                },
                one_slot_drop=key in old,
                four_slot_drop=key in new,
            )
        )
    return result


def render(report, timing):
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 8.1))
    fig.suptitle(
        "One and four waiting slots at recorded delivery cadence",
        x=0.06,
        ha="left",
        fontsize=19,
        fontweight="bold",
        color="#17313b",
    )
    palette = {1: "#b14d38", 4: "#167476"}
    ordered = [(i, m) for i in pace.CPUS for m in pace.MODES]
    labels = [f"{i[-4:]}\n{queue.METHOD[m]}" for i, m in ordered]
    indexed = {(r["id"], r["mode"], r["waiting_slots"]): r for r in timing}
    for capacity, shift in ((1, -0.17), (4, 0.17)):
        for k, (ident, mode) in enumerate(ordered):
            r = indexed[ident, mode, capacity]
            x, color = k + shift, palette[capacity]
            ticks = dict(width=0.29, alpha=0.9, color=color)
            dropped = int(r["queue_drops"])
            axes[0, 0].bar(x, dropped, **ticks, label=f"{capacity} waiting" if k == 0 else None)
            if r["status"] == "complete":
                axes[0, 0].annotate(
                    str(dropped),
                    (x, dropped),
                    xytext=(0, 2),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
            else:
                axes[0, 0].annotate("partial", (x, dropped), ha="center", fontsize=7)
            if not r["age_p50_ms"]:
                continue
            p50, p95, top = (float(r[f"age_{k}_ms"]) for k in ("p50", "p95", "max"))
            axes[0, 1].plot([x, x], [p50, top], color=color, alpha=0.38, linewidth=1)
            axes[0, 1].plot([x, x], [p50, p95], color=color, linewidth=3)
            axes[0, 1].scatter([x, x], [p50, p95], s=14, color=color)
            axes[1, 0].bar(
                x,
                100
                * int(r["native_packets_by_next_delivery"])
                / int(r["native_packets_with_next_delivery"]),
                **ticks,
            )
            wall = float(r["native_wall_p50_ms"])
            cpu = float(r["native_cpu_p50_ms"])
            axes[1, 1].plot([x, x], [cpu, p50], color=color, alpha=0.5)
            axes[1, 1].scatter(x, cpu, color=color, marker="s", s=22)
            axes[1, 1].scatter(x, wall, color=color, marker="^", s=25)
            axes[1, 1].scatter(x, p50, color=color, marker="o", s=23)
    axes[0, 0].set(title="Actual valid visits dropped", ylabel="Visits")
    axes[0, 0].legend(frameon=False)
    axes[0, 1].set(
        title="Packet age · median, p95 and maximum", ylabel="Scheduled delivery to emission (ms)"
    )
    axes[1, 0].set(
        title="Packets emitted before the next physical delivery",
        ylabel="Percent of emitted packets",
        ylim=(0, 104),
    )
    axes[1, 1].set(title="Median native CPU, native wall and packet age", ylabel="Time (ms)")
    axes[1, 1].text(
        0.04,
        0.98,
        "■ CPU    ▲ Native wall    ● Packet age",
        transform=axes[1, 1].transAxes,
        va="top",
        fontsize=9,
    )
    for ax in axes.flat:
        ax.set_xticks(range(len(ordered)), labels)
        ax.grid(axis="y", alpha=0.23)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(rect=(0, 0.01, 1, 0.93), h_pad=2.3)
    for extension in ("png", "pdf"):
        fig.savefig(report / f"buffered-arrival.{extension}", dpi=145)
    plt.close(fig)


def publish_stage(work, report):
    plan = pace.plan(work, report)
    one = list(csv.DictReader(prior_member("paced-replay.csv").read_text().splitlines()))
    timing = [dict(row, waiting_slots=1, origin="historical measured") for row in one]
    previous = pace.readgz(prior_member("paced-events.json.gz"))
    latest, modeled, files = [], [], []
    for ident, spec in plan["cases"].items():
        for mode in pace.MODES:
            path = work / ident / mode
            rows, witness, service, complete, expected = encounter(work, report, mode, ident, spec)
            row = queue.observed(rows, witness, ident, mode, complete, expected)
            timing.append(dict(row, waiting_slots=trial.WAITING, origin="new measured"))
            latest.extend(dict(row, id=ident, mode=mode) for row in rows)
            events = [
                (
                    e["visit"],
                    e["arrival_ns"],
                    "detector" if e["status"] == "processed" else e["status"],
                    e["detector_cpu_ns"],
                    e["detector_wall_ns"],
                )
                for e in expected
            ]
            for use_wall in (False, True):
                for capacity in (1, trial.WAITING):
                    model = queue.simulate(events, 1, capacity, wall=use_wall)
                    modeled.append(
                        dict(
                            id=ident,
                            mode=mode,
                            timing="archived wall" if use_wall else "archived CPU",
                            waiting_slots=capacity,
                            dropped=model["counts"].get("dropped", 0),
                            **queue.timing_ms((x[3] - x[1] for x in model["completed"]), "age"),
                        )
                    )
            for suffix, data in (("service.json", service), ("worker-bounds.json", witness)):
                name = f"{ident}-{mode}-{suffix}"
                save_json(report / name, data)
                files.append(name)
            name = f"{ident}-{mode}-service.log"
            write(report / name, (path / "service.log").read_bytes())
            files.append(name)
    csv_file(report / "buffered-stage.csv", timing)
    csv_file(report / "fixed-service-model.csv", modeled)
    pace.writegz(report / "four-slot-events.json.gz", latest)
    csv_file(report / "drop-identities.csv", compare_drops(previous, latest))
    render(report, timing)
    files.extend(
        (
            "source-lock.json",
            "PROTOCOL.md",
            "buffered-stage.csv",
            "four-slot-events.json.gz",
            "fixed-service-model.csv",
            "drop-identities.csv",
            "buffered-arrival.png",
            "buffered-arrival.pdf",
        )
    )
    files.extend(
        p.name for p in report.glob("*-events.json.gz") if p.name != "four-slot-events.json.gz"
    )
    save_json(
        report / "stage-lock.json",
        dict(
            cases=list(pace.CPUS),
            files={name: _sha(report / name) for name in files},
            one_slot_stage_sha256=trial.BASE_STAGE,
            renderer_sha256=_sha(Path(__file__)),
        ),
    )
    completed = sum(
        r["status"] == "complete" for r in timing if r["waiting_slots"] == trial.WAITING
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="buffered-native-arrival",
            title="Native packet timing with four waiting slots",
            boundary="Actual saved-IQ arrival pacing through verified native output",
            sample=f"Two recordings · {completed}/4 new paced trials · four historical trials",
            note="Same CPU and archive per recording. Native packet age excludes the position fit.",
            seal="stage-lock.json",
            image="buffered-arrival.png",
            pdf="buffered-arrival.pdf",
            csv="buffered-stage.csv",
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "fit-stock", "fit-fifth"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    if args.action == "stage":
        publish_stage(args.work, args.out)
    else:
        refit(args.work, args.out, "control" if args.action == "fit-stock" else "candidate")


if __name__ == "__main__":
    main()
