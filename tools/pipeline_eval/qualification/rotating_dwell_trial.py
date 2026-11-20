"""Freeze rotating hardware-clock dwells and fit the original capture factors."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic

from .. import corpus, whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants import frequency_schedule, rotating_dwell
from . import channel_dwell_worker
from . import frequency_schedule_trial as parent
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .staggered_reconstruction_trial import unavailable

REPORT = parent.REPORT.with_name("rotating-dwell")
PARENT_PIN = "ee7f4d632c7df7a52ff5ad0d1be65c4e31dea91df0fa4ec5879a715c3fdcad12"
CPUS = (14, 15, 16, 17)
LAST_START_S = 780
PREFIX = "rotating_dwell_"
read = whole_iq.read


def new_cases(old):
    excluded = set(old["cases"]) | set(old["selection"]["excluded"])
    inputs, witness = {}, {}
    for dataset, panel in (("DS26", "ds26-common127"), ("DS29", "roof16")):
        ranks = sorted(
            (i for i in corpus._selection(panel)[0] if i.startswith(dataset) and i not in excluded),
            key=lambda i: sha256(f"rotating-dwell-v1:held:{i}".encode()).digest(),
        )
        failed = {}
        for ident in ranks:
            try:
                inputs[ident] = parent.incoming(ident)
            except (KeyError, OSError, ValueError) as error:
                failed[ident] = str(error)
            else:
                witness[dataset] = dict(chosen=ident, rank=ranks, rejected=failed)
                break
        if dataset not in witness:
            raise ValueError(f"no additional authenticated original capture for {dataset}")
    return inputs, witness


def device_schedule(payload):
    case, _, _, document, metadata, _ = payload
    devices = {p["visit_index"]: p["valid_start_counter"] for p in document["source"]["probes"]}
    sample_rate = document["source"]["sample_rate_hz"]
    origin = document["clock_anchor"]["sample_counter"]
    last = document["last_sample_counter"]
    return {
        f"rotate{n}": rotating_dwell.schedule(
            case["id"], metadata, devices, origin, last, sample_rate, n
        )
        for n in (2, 4)
    }


def freeze(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("rotating dwell already sealed its prospective roster")
    receipt = sealed(parent.REPORT, "prediction-lock.json", PARENT_PIN)
    old = read(parent.REPORT / "plan.json")
    if receipt["cases"] != old["cases"] or len(old["cases"]) != 8:
        raise ValueError("prior phase-release comparison roster changed")
    release, _ = parent.timing_inputs()
    if any(release[k] != old[k] for k in ("receiver", "receiver_files")):
        raise ValueError("rotating dwell must use exactly the earlier installed phase release")
    further, witness = new_cases(old)
    cases = {i: parent.incoming(i) for i in old["cases"]} | further
    work.mkdir(exist_ok=False)
    tasks, schedules, events = [], {}, {}
    for i, (ident, values) in enumerate(cases.items()):
        case, request, native, base, metadata, clocks = values
        resolved = device_schedule(values)
        schedules[ident] = {k: v[0] for k, v in resolved.items()}
        events[ident] = {k: v[1] for k, v in resolved.items()}
        modes = ["rotate2", "rotate4"]
        if ident in further:
            fixed = frequency_schedule.schedules(ident, metadata, clocks)
            for mode in ("lanes2", "lanes4", "full"):
                modes.append(mode)
                schedules[ident][mode] = fixed[mode]
        assigned = parent.capture_bursts_trial.stage(
            work,
            Path(channel_dwell_worker.__file__),
            CPUS[i % len(CPUS)],
            modes,
            case,
            request,
            native,
            base,
            metadata,
            {k: v for k, v in schedules[ident].items() if k != "full"},
        )
        for row in assigned:
            leaf = work / ident / row["condition"]
            write(leaf / "receiver-path.txt", (release["receiver"] + "\n").encode())
            row.update(
                method=PREFIX + row["condition"],
                cohort="prospective2" if ident in further else "mechanism8",
            )
            tasks.append(row)
    save_json(REPORT / "schedule.json", schedules)
    save_json(REPORT / "dwell-events.json", events)
    owned = (
        Path(__file__),
        Path(rotating_dwell.__file__),
        Path(frequency_schedule.__file__),
        Path(channel_dwell_worker.__file__),
        Path(parent.capture_bursts_trial.__file__),
        Path(parent.service.__file__),
        REPORT / "PROTOCOL.md",
    )
    plan = dict(
        cases=list(cases),
        mechanism8=old["cases"],
        prospective2=list(further),
        inputs=witness,
        tasks=tasks,
        parent_prediction_sha256=PARENT_PIN,
        sources={str(path.relative_to(ROOT)): _sha(path) for path in owned},
        schedule_sha256=_sha(REPORT / "schedule.json"),
        events_sha256=_sha(REPORT / "dwell-events.json"),
        receiver=release["receiver"],
        receiver_files=release["receiver_files"],
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        service_limit_s=parent.service.LIMIT,
        last_start_s=LAST_START_S,
    )
    save_json(REPORT / "plan.json", plan)
    print("frozen", plan["cases"], _sha(REPORT / "plan.json"), flush=True)
    return plan


def run(work):
    plan = freeze(work)
    start = monotonic()

    def lane(cpu):
        records = []
        for row in plan["tasks"]:
            if row["cpu"] != cpu:
                continue
            if monotonic() - start >= LAST_START_S:
                records.append(unavailable(row, "prospective last-start horizon reached"))
                continue
            result = parent.service.service(work, row)
            path = work / row["id"] / row["condition"] / "geometry.json"
            records.append(dict(result, graph=read(path) if path.is_file() else None))
        return records

    with ThreadPoolExecutor(len(CPUS)) as pool:
        rows = [row for group in pool.map(lane, CPUS) for row in group]
    pack(REPORT / "predictions.jsonl.gz", rows)
    members = ("plan.json", "schedule.json", "dwell-events.json", "predictions.jsonl.gz")
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
