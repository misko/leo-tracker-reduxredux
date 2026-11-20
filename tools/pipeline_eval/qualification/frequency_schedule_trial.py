"""Freeze full-pass original RF schedules and run the installed compact receiver."""

import argparse
import csv
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

from .. import corpus, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import capture_bursts, frequency_schedule
from . import capture_bursts_trial, channel_dwell_trial, scheduled_capture_waveform
from . import support_cross_trial as service
from .fresh_replay_results import sealed
from .full_v5_check import BULK, _sha
from .phase_support_results import pack
from .staggered_reconstruction_trial import unavailable

SCREEN = capture_bursts_trial.REPORT.parents[1]
REPORT = SCREEN / "original-support/frequency-schedule"
TIMING = SCREEN / "antenna-confirmation/capture-whole"
TIMING_PIN = "84f9aa52911b391a8a23c60a57dd0f3e8d4106060ba94fb7e92b40215c829d33"
OVERLAP_PIN = "60e62bc21a0c39fc73c543fe52c33eee7e0af4a094fa974fcd9108d1c4c2a4bd"
ANCHOR, OVERLAP = "DS29-0082", "DS26-0162"
CPUS = (18, 19, 20, 21)
HORIZON = 900
PREFIX = "frequency_schedule_"
read = whole_iq.read


def timing_inputs():
    lock = sealed(TIMING, "prediction-lock.json", TIMING_PIN)

    def get(name):
        return whole_iq.checked(TIMING / name, lock["files"][name])

    source = read(get("source-lock.json"))
    if (
        lock["cases"] != [ANCHOR]
        or whole_iq.receiver_identity(Path(source["receiver"])) != source["receiver_files"]
    ):
        raise ValueError("the measured original detector and compact installation must match")
    with get("timing.csv").open(newline="") as stream:
        timings = {
            int(r["visit"]): float(r["cpu_ms"]) / 1000
            for r in csv.DictReader(stream)
            if r["status"] == "processed"
        }
    if len(timings) != 4868 or min(timings.values()) <= 0:
        raise ValueError("missing genuine detector CPU timing on an anchor visit")
    return source, timings


def incoming(ident):
    case, request = whole_iq.binding(ident)
    path = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    document = read(path)
    src = document["source"]
    if (
        src["session_id"],
        src["sample_rate_hz"],
        src["probe_ms"],
        document["provenance"]["run_id"],
    ) != (
        case["session_id"],
        10_000_000,
        20,
        case["run_id"],
    ):
        raise ValueError("recording disagrees with original complete native identity")
    metadata = capture_bursts.inventories(document)
    clocks = [r["monotonic_ns"] for r in document["delivery_clocks"]]
    lanes = defaultdict(list)
    for visit, channel in metadata:
        lanes[channel].append(clocks[visit])
    if set(lanes) != set(frequency_schedule.CHANNELS) or any(
        times[-1] - times[0] < 240_000_000_000 for times in lanes.values()
    ):
        raise ValueError("all eight RF lanes need authentic opportunities spanning ≥240 seconds")
    return case, request, path, document, metadata, clocks


def choose():
    old = (capture_bursts_trial.REPORT, channel_dwell_trial.REPORT)
    pins = {
        str((directory / "prediction-lock.json").relative_to(ROOT)): _sha(
            directory / "prediction-lock.json"
        )
        for directory in old
    }
    excluded = {ANCHOR, OVERLAP}
    for directory in old:
        excluded.update(sealed(directory, "prediction-lock.json")["cases"])
    known, selection = {}, {}
    for dataset, panel in (("DS26", "ds26-common127"), ("DS29", "roof16")):
        ranked = sorted(
            (i for i in corpus._selection(panel)[0] if i.startswith(dataset) and i not in excluded),
            key=lambda i: frequency_schedule.rank("holdout", i),
        )
        picked, rejects = [], {}
        for ident in ranked:
            try:
                known[ident] = incoming(ident)
            except (KeyError, OSError, ValueError) as error:
                rejects[ident] = str(error)
            else:
                picked.append(ident)
                if len(picked) == 3:
                    break
        if len(picked) != 3:
            raise ValueError(f"{dataset} insufficient authentic held recordings: {rejects}")
        selection[dataset] = dict(ranked=ranked, rejected=rejects, chosen=picked)
    return known, dict(provenance=pins, excluded=sorted(excluded), selection=selection)


def recorded_periodic(case, metadata):
    plan, _ = scheduled_capture_waveform.metadata(case)
    archived = read(
        whole_iq.checked(scheduled_capture_waveform.WORK / "schedule.json", OVERLAP_PIN)
    )
    if plan != archived or any(plan[visit][0] != channel for visit, channel in metadata):
        raise ValueError("raw overlap and original archived physical RF mapping disagree")
    return [visit for visit, _ in metadata if plan[visit][-1] is True], OVERLAP_PIN


def freeze(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("frequency trial already froze its prospective schedule")
    release, timing = timing_inputs()
    known, selection = choose()
    inputs = {ANCHOR: incoming(ANCHOR), OVERLAP: incoming(OVERLAP)} | known
    if inputs[ANCHOR][0]["native"]["sha256"] != release["original"]["native"]["sha256"]:
        raise ValueError("timed visits do not correspond to the archived anchor factors")
    if set(timing) != {v for v, _ in inputs[ANCHOR][4]}:
        raise ValueError("exact timing cadence differs from the anchor valid-visit ledger")
    work.mkdir(exist_ok=False)
    scheduled, witness, tasks = {}, {}, []
    for index, (ident, payload) in enumerate(inputs.items()):
        case, request, native, document, metadata, clocks = payload
        assignments = frequency_schedule.schedules(ident, metadata, clocks)
        witness[ident] = dict(
            native_source=str(native),
            native_sha256=case["native"]["sha256"],
            clock_sha256=whole_iq.recording.digest(document["delivery_clocks"]),
            span_s=(clocks[-1] - clocks[0]) / 1e9,
            selected_rf={str(n): frequency_schedule.channels(ident, n) for n in (2, 4)},
            sample_clock_hz=document["source"]["sample_rate_hz"],
        )
        modes = list(frequency_schedule.MODES)
        if ident == OVERLAP:
            picked, dispatch_hash = recorded_periodic(case, metadata)
            assignments["periodic4"] = picked
            witness[ident]["raw_overlap_dispatch_sha256"] = dispatch_hash
            modes.append("periodic4")
        scheduled[ident] = assignments
        rows = capture_bursts_trial.stage(
            work,
            release["receiver"],
            CPUS[index % len(CPUS)],
            modes,
            case,
            request,
            native,
            document,
            metadata,
            {k: v for k, v in assignments.items() if k != "full"},
        )
        for row in rows:
            mode = row["condition"]
            row.update(
                method=PREFIX + mode,
                cohort="anchor"
                if ident == ANCHOR
                else "raw-overlap"
                if ident == OVERLAP
                else "held6",
            )
            tasks.append(row)
    members = (
        Path(__file__),
        Path(frequency_schedule.__file__),
        Path(capture_bursts_trial.__file__),
        Path(capture_bursts.__file__),
        Path(service.__file__),
        Path(service.margin_admission_trial.__file__),
        REPORT / "PROTOCOL.md",
    )
    save_json(REPORT / "schedule.json", scheduled)
    plan = dict(
        cases=list(inputs),
        held=list(known),
        tasks=tasks,
        selection=selection,
        inputs=witness,
        source_sha256={str(path.relative_to(ROOT)): _sha(path) for path in members},
        timing_lock_sha256=TIMING_PIN,
        schedule_sha256=_sha(REPORT / "schedule.json"),
        service_limit_s=service.LIMIT,
        last_start_s=HORIZON,
        receiver=release["receiver"],
        receiver_files=release["receiver_files"],
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
    )
    save_json(REPORT / "plan.json", plan)
    print("frozen", plan["cases"], _sha(REPORT / "plan.json"), flush=True)
    return plan


def run(work):
    plan = freeze(work)
    start = monotonic()
    order = ("full", "lanes2", "bursts2", "periodic4", "lanes4", "bursts4")

    def lane(cpu):
        jobs = [r for r in plan["tasks"] if r["cpu"] == cpu]
        return [
            service.service(work, row)
            if monotonic() - start < HORIZON
            else unavailable(row, "prospective last-start horizon reached")
            for row in sorted(jobs, key=lambda r: order.index(r["condition"]))
        ]

    with ThreadPoolExecutor(len(CPUS)) as pool:
        results = [r for lane in pool.map(lane, CPUS) for r in lane]
    pack(REPORT / "positions.jsonl.gz", results)
    members = ("plan.json", "schedule.json", "positions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=plan["cases"],
            elapsed_s=monotonic() - start,
            files={name: _sha(REPORT / name) for name in members},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
