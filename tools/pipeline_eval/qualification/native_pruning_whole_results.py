"""Seal actual complete four-region timing and fit the verified emitted support."""

import argparse
import csv
import gzip
import json
from hashlib import sha256
from pathlib import Path

import matplotlib

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS
from . import native_pruning_whole as trial
from . import support_cross_trial
from .arrival_queue_results import observed, terminal
from .fractional_runtime_whole import verify_request
from .frontier_whole_replay_results import fingerprint as archived_probe_hash
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, sealed
from .native_hotpath_results import distribution
from .phase_support_results import pack

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

OVERLAY = "native-pruning-whole-position"


def csv_file(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def matching_emissions(pruned, dense):
    common = pruned.keys() & dense.keys()
    keys = ("status", "full_visit_sha256")
    if any(any(pruned[i][k] != dense[i][k] for k in keys) for i in common):
        raise ValueError("actual overlapping native packets differ across whole replays")
    return common


def emitted_support(probes, visits):
    result = []
    for visit in sorted(visits):
        pair = probes.get(visit, ())
        if [r["receiver_id"] for r in pair] != [0, 1]:
            raise ValueError("each emitted physical visit requires both receiver rows")
        result.extend(pair)
    return result


def comparisons(report, rows, common):
    per_visit = {role: {r["visit"]: r for r in item["timing"]} for role, item in rows.items()}
    stage = {
        name: distribution(
            [per_visit["pruned"][i][name] - per_visit["dense"][i][name] for i in common]
        )
        for name in trial.STAGES
    }
    first, second = (rows[role]["emitted"] for role in trial.ROLES)
    endpoints = {
        name.removesuffix("_ns") + "_ms": distribution(
            [(first[i][name] - second[i][name]) / 1e6 for i in common]
        )
        for name in ("native_cpu_ns", "native_wall_ns")
    }
    endpoints["age_ms"] = distribution(
        [(first[i]["emitted_ns"] - second[i]["emitted_ns"]) / 1e6 for i in common]
    )
    old = trial.pace.REPORT
    parent = whole_iq.read(old / "stage-lock.json")["files"]
    timing = whole_iq.checked(old / "paced-replay.csv", parent["paced-replay.csv"])
    with timing.open() as stream:
        (earlier,) = [
            r for r in csv.DictReader(stream) if (r["id"], r["mode"]) == (trial.CASE, "control")
        ]
    receipts = trial.pace.readgz(
        whole_iq.checked(old / "paced-events.json.gz", parent["paced-events.json.gz"])
    )
    admitted = [
        r
        for r in receipts
        if (r["id"], r["mode"], r["outcome"]) == (trial.CASE, "control", "emitted")
    ]
    if len(admitted) != int(earlier["native_packets_emitted"]):
        raise ValueError("historical emitted counts differ from their measurements")
    save_json(
        report / "comparison.json",
        dict(
            common_actual_emissions=len(common),
            paired_pruned_minus_dense_ms=endpoints,
            paired_stage_cpu_delta_ms=stage,
            order=list(trial.ROLES),
            pinned_cpus=[trial.MAIN, trial.HELPER],
            archived_control=dict(
                earlier,
                caller_cpu=18,
                execution="separate earlier single-caller service",
                native_within_20ms=sum(r["native_wall_ns"] <= 20_000_000 for r in admitted),
                age_within_20ms=sum(
                    r["emitted_ns"] - r["arrival_ns"] <= 20_000_000 for r in admitted
                ),
            ),
            archived_sha256={
                name: parent[name] for name in ("paced-replay.csv", "paced-events.json.gz")
            },
        ),
    )


def read(work):
    report = trial.REPORT
    lock = trial.pace.plan(work, report)
    selected = lock["cases"][trial.CASE]["modes"]
    rows, live, stats = {}, {}, []
    for role in trial.ROLES:
        spec = selected[role]
        events = trial.pace.readgz(whole_iq.checked(report / spec["events"], spec["sha256"]))
        attempt = work / trial.CASE / role
        trace, witness, service, complete = terminal(attempt, events)
        if not complete:
            raise ValueError(f"actual {role} whole replay did not complete")
        timing = trial.pace.readgz(attempt / "native-stages.json.gz")
        emitted = {r["visit"]: r for r in trace if r["outcome"] == "emitted"}
        if [r["visit"] for r in timing] != sorted(emitted):
            raise ValueError("actual numerical stage clocks differ from the emitted roster")
        if any(row.keys() != {"visit", *trial.STAGES} for row in timing):
            raise ValueError("raw stage telemetry has unexpected fields")
        if any(v["status"] != "processed" for v in emitted.values()):
            raise ValueError("hardware-invalid visit entered native output")
        payload = [
            dict(
                visit=r["visit"],
                status=r["status"],
                outcome=r["outcome"],
                sha256=r["full_visit_sha256"] if r["outcome"] != "queue_drop" else None,
            )
            for r in trace
        ]
        rows[role] = dict(
            trace=trace,
            timing=timing,
            packets=payload,
            emitted=emitted,
            witness=witness,
            service=service,
            events=events,
        )
        live[role] = emitted.keys()
        for name in trial.STAGES:
            values = [r[name] for r in timing]
            stats.append(
                dict(role=role, stage=name, total_cpu_s=sum(values) / 1000, **distribution(values))
            )
        status = observed(trace, witness, trial.CASE, role, complete, events)
        save_json(
            report / f"{role}-raw.json",
            status
            | dict(
                native_within_20ms=sum(r["native_wall_ns"] <= 20_000_000 for r in emitted.values()),
                age_within_20ms=sum(
                    r["emitted_ns"] - r["arrival_ns"] <= 20_000_000 for r in emitted.values()
                ),
            ),
        )
        trial.pace.writegz(report / f"{role}-trace.json.gz", trace)
        trial.pace.writegz(report / f"{role}-stages.json.gz", timing)
        save_json(report / f"{role}-service.json", service)
        save_json(report / f"{role}-witness.json", witness)
    control, pruned = live["dense"], live["pruned"]
    paired = matching_emissions(rows["pruned"]["emitted"], rows["dense"]["emitted"])
    save_json(
        report / "parity.json",
        dict(
            schedule=len(rows["pruned"]["trace"]),
            exact_common=len(paired),
            shared_status_exact=True,
            released={role: len(live[role]) for role in trial.ROLES},
            only_pruned=sorted(pruned - control),
            only_dense=sorted(control - pruned),
            both_payload={
                role: trial.pace.fingerprint(rows[role]["packets"]) for role in trial.ROLES
            },
        ),
    )
    csv_file(report / "native-stages.csv", stats)
    trial.pace.writegz(report / "packet-status.json.gz", {k: v["packets"] for k, v in rows.items()})
    comparisons(report, rows, paired)
    return lock, rows


def complete_archive(lock, events):
    parent = trial.pace.PARENT
    original = whole_iq.read(
        whole_iq.checked(parent / "prediction-lock.json", lock["parent_prediction_sha256"])
    )
    members = original["files"]
    release = whole_iq.read(
        whole_iq.checked(parent / "source-lock.json", members["source-lock.json"])
    )
    archive_name = f"native/control/{trial.CASE}.json.gz"
    blob = gzip.decompress(
        whole_iq.checked(parent / archive_name, members[archive_name]).read_bytes()
    )
    document = json.loads(blob)
    predictions = sealed(parent, "prediction-lock.json", "positions.jsonl.gz")
    (archived,) = [
        r
        for r in predictions
        if r["id"] == trial.CASE and r["method"] == trial.pace.whole_center_union.BASELINE
    ]
    if sha256(blob).hexdigest() != archived["native_sha256"]:
        raise ValueError("complete archived detector and measured original stock fit differ")
    probes = {}
    for row in document["source"]["probes"]:
        probes.setdefault(row["visit_index"], []).append(row)
    name = "visits.jsonl.gz"
    count = 0
    raw = whole_iq.checked(parent / name, members[name])
    with gzip.open(raw, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if (row["id"], row["role"]) != (trial.CASE, "control"):
                continue
            expected = events[count]
            if any(row[k] != expected[k] for k in ("visit", "status", "full_visit_sha256")):
                raise ValueError(
                    "stock packet reference differs from the complete original witness"
                )
            for actual, saved in zip(probes.get(count, ()), row["probes"], strict=True):
                if (
                    actual["receiver_id"] != saved["receiver_id"]
                    or archived_probe_hash(actual["candidates"]) != saved["payload_sha256"]
                ):
                    raise ValueError(
                        "archived native factors differ from the exact original packet"
                    )
            count += 1
    if count != len(events):
        raise ValueError("stock packet reference is incomplete")
    return document, probes, archived, release


def position(work, lock, data):
    pruned = data["pruned"]
    base, probes, reference, release = complete_archive(lock, pruned["events"])
    chosen = sorted(pruned["emitted"])
    actual = emitted_support(probes, chosen)
    identity = trial.pace.recording_to_v5.digest(
        [trial.METHOD, pruned["witness"]["output_sha256"], chosen]
    )
    detector = lock["assets"][f"pruned:{trial.DETECTOR}"]["sha256"]
    document = dict(
        base,
        source=dict(base["source"], probes=actual, analysis_manifest_sha256=identity),
        provenance=dict(
            base["provenance"],
            processed_windows=len(chosen),
            detector_sha256="sha256:" + detector,
            run_id="replay-" + identity[7:39],
            scope="Stock four native packets verified after actual active-set arrival replay",
        ),
    )
    case, original = whole_iq.binding(trial.CASE)
    roster = release["cases"][trial.CASE]
    condition = "pruned-position"
    directory = work / trial.CASE / condition
    stored = directory / "recording"
    stored.mkdir(parents=True, exist_ok=False)
    native, request = stored / "native.json", stored / "request.json"
    write(native, encoded(document) + b"\n")
    bound = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    verify_request(whole_iq.read(request), original, native_path=native, native_sha256=bound)
    row = dict(
        id=trial.CASE,
        condition=condition,
        mode="matched-tile",
        method=trial.METHOD,
        cpu=trial.MAIN,
        tile=roster["tile"],
        catalog_sha256=roster["catalog_sha256"],
        paired_capture_sha256=roster["capture_native_sha256"],
        original_request_sha256=roster["request_sha256"],
        native_sha256=_sha(native),
        prepared_request_sha256=_sha(request),
        actual_verified_visited=len(chosen),
        exact_full_stock_support=len(chosen) == len(probes),
        arrival_trace_sha256=pruned["witness"]["output_sha256"],
    )
    save_json(
        trial.REPORT / "position-input-lock.json",
        dict(
            actual=row,
            original_stock_native=reference["native_sha256"],
            memory_limit=whole_iq.MEMORY,
            seconds=support_cross_trial.LIMIT,
            source_sha256=_sha(Path(__file__)),
        ),
    )
    save_json(directory / "plan.json", {"receiver": release["receiver"]})
    save_json(directory / "raw.json", dict(native_sha256=bound, request_sha256=_sha(request)))
    measured = support_cross_trial.service(work, row)
    pack(trial.REPORT / "positions.jsonl.gz", [measured, reference])
    return measured, reference


def stages(report):
    fig, (left, right) = plt.subplots(1, 2, figsize=(9.7, 4.25))
    labels = ("Active set", "Dense")
    rows = [whole_iq.read(report / f"{role}-raw.json") for role in trial.ROLES]
    stages = [
        r for r in csv.DictReader((report / "native-stages.csv").open()) if r["stage"] == "coarse"
    ]
    left.bar([0, 1], [float(r["p50"]) for r in stages], color=("#167f73", "#52728b"), width=0.56)
    left.scatter([0, 1], [float(r["p95"]) for r in stages], color="#30343b", marker="D", zorder=3)
    left.set_ylabel("Summed coarse CPU (ms)")
    for x, raw in enumerate(rows):
        n = raw["native_packets_emitted"]
        right.bar(
            x - 0.17,
            100 * raw["native_within_20ms"] / n,
            width=0.31,
            color="#1e7d71",
            label="Detector" if x == 0 else None,
        )
        right.bar(
            x + 0.17,
            100 * raw["age_within_20ms"] / n,
            width=0.31,
            color="#69879a",
            label="Arrival to emission" if x == 0 else None,
        )
    right.set_ylabel("Emissions at or below 20 ms (%)")
    right.legend(loc="lower center", ncol=2, frameon=False, fontsize=8)
    right.set_ylim(0, 103)
    for axis in (left, right):
        axis.set_xticks([0, 1], labels)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.2)
    fig.text(
        0.06,
        0.96,
        "Exact wide GLRT on one complete recorded arrival",
        fontsize=15.5,
        fontweight="bold",
    )
    fig.text(
        0.06,
        0.90,
        "DS26-0197 · Active set first, dense second · Four regions on both receivers",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.09, top=0.81, bottom=0.15, wspace=0.31)
    fig.savefig(report / "stage.png", dpi=170)
    fig.savefig(report / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    report = trial.REPORT
    lock, data = read(work)
    stages(report)
    raw = (
        "source-lock.json",
        "native-stages.csv",
        "packet-status.json.gz",
        "parity.json",
        "comparison.json",
        "stage.png",
        "stage.pdf",
        *(
            f"{role}-{name}"
            for role in trial.ROLES
            for name in (
                "raw.json",
                "trace.json.gz",
                "stages.json.gz",
                "service.json",
                "witness.json",
            )
        ),
    )
    save_json(
        report / "raw-lock.json", dict(files={p: _sha(report / p) for p in raw}, case=trial.CASE)
    )
    result, archive = position(work, lock, data)
    (authority,) = held_references(None, [trial.CASE])[1]
    scores = [fit(r, authority, arm) for r in (result, archive) for arm in ARMS]
    csv_file(report / "scores.csv", scores)
    files = (
        "positions.jsonl.gz",
        "position-input-lock.json",
        "raw-lock.json",
        "scores.csv",
        "parity.json",
    )
    save_json(
        report / "figure-lock.json",
        dict(cases=[trial.CASE], files={n: _sha(report / n) for n in files}),
    )
    matches = ["paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile"]
    labels = [
        ("one", "Paced active-set four", trial.METHOD),
        ("stock", "Archived full stock four", archive["method"]),
    ]
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=OVERLAY,
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    title="Exact four-region receiver on one recorded arrival sequence",
                    caption=(
                        "The live fit uses exact emitted support on CPU0/1. Archived stock uses "
                        "all valid packets. The four v5 roles use capture-era factors."
                    ),
                    provenance=list(files[1:]),
                    series=[
                        dict(
                            key=k,
                            label=label,
                            file=files[0],
                            value=method,
                            native_field="paired_capture_sha256",
                            match=matches,
                        )
                        for k, label, method in labels
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=local_output)
    publish(p.parse_args().work)
