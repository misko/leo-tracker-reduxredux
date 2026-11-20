"""Seal blinded native recovery trials and score on their exact archived controls."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import conditional_support_recovery as method
from ..variants import phase_capture
from . import native_joint_full as full
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .native_joint_results import geodata
from .prefix_figures import csv_file

joint = full.base
OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/recovery/conditional-support"
WORKER = Path(__file__).with_name("conditional_support_worker.py")
IDS = (
    "DS26-0197",
    "DS26-0223",
    "DS26-0279",
    "DS26-0307",
    "DS29-0127",
    "DS29-0174",
    "DS26-0070-omitted",
)
CPUS = (13, 14, 15)
CAP = 60


def jobs():
    lock = joint.phase._read(full.REPORT / "prediction-lock.json")
    joint.secant_full._verify_files(full.REPORT, lock["files"])
    archived = read_predictions(full.REPORT / "positions.jsonl.gz")
    plan = joint.phase._read(full.REPORT / "plan.json")
    queries = {r["id"]: r for r in plan["cases"]}
    inputs = joint.phase.frozen_inputs()
    rows = []
    for ident in IDS:
        source = queries[ident]
        item = inputs.get(source["recording"]) or joint.native._load_case(source["recording"])
        packet, paths = joint.native.request(item, "native", offer=source["packet"]["offer"])
        if (
            packet != source["packet"]
            or joint.phase.corpus._sha(encoded(packet)) != archived[ident]["input_sha256"]
        ):
            raise ValueError("candidate request does not bind original archive")
        rows.append((source, paths, archived[ident]))
    metadata = dict(
        frozen=joint.sources(joint.BUNDLE),
        cpus=list(CPUS),
        cap_s=CAP,
        cases=[x[0] for x in rows],
        control_sha256=lock["files"]["positions.jsonl.gz"],
        sources={
            str(p.relative_to(ROOT)): joint.phase.digest(p)
            for p in (
                Path(__file__),
                Path(method.__file__),
                Path(phase_capture.__file__),
                WORKER,
                OUTPUT / "PROTOCOL.md",
            )
        },
    )
    return rows, metadata


def measure(task, cpu):
    query, paths, reference = task
    command = joint.command(cpu, paths, joint.BUNDLE)
    command[command.index(str(joint.WORKER))] = str(WORKER)
    for module in (method, phase_capture):
        path = Path(module.__file__)
        command[-3:-3] = [
            "--ro-bind",
            str(path),
            "/worker/tools/pipeline_eval/variants/" + path.name,
        ]
    packed = encoded(query["packet"])
    start = perf_counter()
    try:
        p = subprocess.run(command, input=packed, capture_output=True, check=True, timeout=CAP)
        result = json.loads(p.stdout)
        if result["observation_sha256"] != reference.get("observation_sha256"):
            raise ValueError("Graph differs from nominal control")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        message = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1500:]
        result = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=message or str(err),
                boundary=method.BOUNDARY,
                metrics={},
                arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
            )
        )
    validate_result(result["result"])
    record = {
        k: reference[k]
        for k in ("id", "recording", "tile", "native_sha256", "catalog_sha256", "input_sha256")
    }
    record.update(result, cpu=cpu, worker_wall_s=perf_counter() - start, method=method.METHOD)
    r = record.get("recovery", {})
    print(
        record["id"],
        record["result"]["status"],
        "attempted",
        r.get("attempted"),
        "proposals",
        [p["norad"] for p in r.get("proposals", [])],
        round(record["worker_wall_s"], 2),
        flush=True,
    )
    return record


def run(work):
    tasks, manifest = jobs()
    work.mkdir(parents=True, exist_ok=False)
    save_json(OUTPUT / "blind-plan.json", manifest)
    start = perf_counter()

    def lane(i):
        for task in tasks[i :: len(CPUS)]:
            row = measure(task, CPUS[i])
            save_json(work / (row["id"] + ".json"), row)

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, range(len(CPUS))))
    if jobs()[1] != manifest:
        raise ValueError("source or input changed during blind execution")
    rows = [joint.phase._read(work / (i + ".json")) for i in IDS]
    files = dict(
        **{
            "positions.jsonl.gz": pack(OUTPUT, "positions.jsonl.gz", rows),
            "blind-plan.json": joint.phase.digest(OUTPUT / "blind-plan.json"),
        }
    )
    save_json(
        OUTPUT / "prediction-lock.json",
        dict(cases=list(IDS), files=files, wall_s=perf_counter() - start),
    )


def score():
    lock = joint.phase._read(OUTPUT / "prediction-lock.json")
    joint.secant_full._verify_files(OUTPUT, lock["files"])
    rows = read_predictions(OUTPUT / "positions.jsonl.gz")
    tasks, metadata = jobs()
    if tuple(rows) != IDS or metadata != joint.phase._read(OUTPUT / "blind-plan.json"):
        raise ValueError("cannot score a different sealed attempt")
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in joint.phase.corpus.references(panel)
    }
    scores, controls = [], []
    for _, _, control in tasks:
        row = rows[control["id"]]
        controls.append(control)
        truth = refs[row["recording"]]["truth"]
        margin = roi_margin(truth, row["tile"])
        cohort = (
            "omitted"
            if row["id"].endswith("-omitted")
            else ("diagnostic" if row["id"] in IDS[:2] else "confirmation")
        )
        if (margin < 0) != (cohort == "omitted"):
            raise ValueError("recorded tile relation did not verify")
        for arm in ARMS:
            for record in (control, row):
                scores.append(
                    dict(
                        id=row["id"],
                        cohort=cohort,
                        method=record["method"],
                        arm=arm,
                        tile_margin_km=margin,
                        **geodata(record, arm, truth),
                    )
                )
    pack(OUTPUT, "control-positions.jsonl.gz", controls)
    csv_file(OUTPUT / "scores.csv", scores)
    save_json(OUTPUT / "scores.json", scores)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path)
    args = p.parse_args()
    run(args.work) if args.work else score()
