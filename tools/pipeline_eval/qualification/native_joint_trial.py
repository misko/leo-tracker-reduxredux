"""Bound and seal matched native GLRT to joint-orbit position replays."""

import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, validate_result
from ..variants import joint_orbits
from . import native_lean_eval as native
from . import phase_confirmation as phase
from . import secant_full
from .native_joint_worker import BOUNDARY

REPORT = secant_full.REPORT.parent / "inference/native-joint"
NATIVE = REPORT.with_name("native-lean")
JOINT = REPORT.with_name("joint-orbits")
BUNDLE = Path("/tmp/native-lean-final.bTK1zt/work/deployed-source")
WORKER = Path(__file__).with_name("native_joint_worker.py")
METHOD = "native_joint_orbits"
CPUS = (12, 13)
CAP = 60
SEED = "native-joint-confirm-v1:"


def sources(bundle):
    native_lock = phase._read(NATIVE / "source-lock.json")
    if native.check_sources() != native_lock:
        raise ValueError("the native implementation differs from its source lock")
    joint_lock = phase._read(JOINT / "source-lock.json")
    secant_full._verify_files(native.ROOT, joint_lock["files"])
    deployment = phase._read(NATIVE / "deployment.json")
    for container, file in deployment["files"].items():
        path = bundle / container.removeprefix("/worker/").removeprefix("/source/")
        if phase.digest(path) != file["sha256"]:
            raise ValueError("the deployed native source differs from its inventory")
    return dict(
        native=phase.digest(NATIVE / "source-lock.json"),
        joint=phase.digest(JOINT / "source-lock.json"),
        deployment=phase.digest(NATIVE / "deployment.json"),
        wrapper=phase.digest(WORKER),
        runner=phase.digest(Path(__file__)),
        protocol=phase.digest(REPORT / "PROTOCOL.md"),
    )


def roster(inputs, prior_joint):
    remaining = inputs.keys() - set(native.CASES) - set(prior_joint)
    reserve = []
    for dataset, count in (("DS26", 2), ("DS29", 1)):
        eligible = (
            i for i in remaining if i.startswith(dataset + "-") and inputs[i].get("recording")
        )
        reserve.extend(
            sorted(eligible, key=lambda i: phase.corpus._sha((SEED + i).encode()))[:count]
        )
    if len(reserve) != 3:
        raise ValueError("expected three new matched recording IDs")
    return dict(primary=list(native.CASES), confirmation=reserve, wrong_offer=[native.WRONG_ID])


def jobs(inputs):
    selected = roster(inputs, phase._read(JOINT / "source-lock.json")["cases"])
    for cohort, ids in selected.items():
        for ident in ids:
            recording = native.SMOKE[0] if cohort == "wrong_offer" else ident
            item = inputs[recording]
            offer = None
            if cohort == "wrong_offer":
                offers = phase._read(phase.corpus.FROZEN / "roof-four-offers.json")[recording]
                if offers["catalog_sha256"] != item["catalog"]["sha256"]:
                    raise ValueError("alternate tile catalogue differs")
                (offer,) = (r for r in offers["regions"] if r["id"] == "r0")
            packet, paths = native.request(item, "native", offer=offer)
            yield dict(id=ident, recording=recording, cohort=cohort, packet=packet), paths


def command(cpu, paths, bundle):
    argv = native.command(cpu, paths, source=bundle)
    argv[argv.index(str(bundle / "main.py"))] = str(WORKER)
    for source, name in (
        (bundle / "main.py", "native_lean.py"),
        (Path(joint_orbits.__file__), "joint_orbits.py"),
    ):
        argv[-3:-3] = ["--ro-bind", str(source), f"/worker/tools/pipeline_eval/variants/{name}"]
    return argv


def attempt(query, paths, cpu, bundle):
    packet = query["packet"]
    raw = encoded(packet)
    began = perf_counter()
    try:
        process = subprocess.run(
            command(cpu, paths, bundle), input=raw, capture_output=True, timeout=CAP, check=True
        )
        out = json.loads(process.stdout)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        message = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1800:]
        out = dict(
            result=dict(
                status="timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed",
                reason=message or str(error),
                boundary=BOUNDARY,
                metrics={},
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            )
        )
    validate_result(out["result"])
    row = {k: v for k, v in query.items() if k != "packet"}
    row.update(
        out,
        method=METHOD,
        cpu=cpu,
        worker_wall_s=perf_counter() - began,
        input_sha256=phase.corpus._sha(raw),
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        tile=packet["offer"],
    )
    print(row["id"], row["result"]["status"], round(row["worker_wall_s"], 3), flush=True)
    return row


def run(bundle, work):
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("expected CPU 12 and 13")
    source = sources(bundle)
    frames = list(jobs(phase.frozen_inputs()))
    work = local_output(work)
    work.mkdir(exist_ok=False, parents=True)
    plan = dict(sources=source, cases=[row for row, _ in frames], cpus=list(CPUS), timeout_s=CAP)
    save_json(work / "plan.json", plan)
    save_json(REPORT / "roster.json", plan)

    def lane(cpu, records):
        for query, paths in records:
            save_json(work / f"{query['id']}.json", attempt(query, paths, cpu, bundle))

    started = perf_counter()
    with ThreadPoolExecutor(2) as pool:
        done = [pool.submit(lane, cpu, frames[i::2]) for i, cpu in enumerate(CPUS)]
        for job in done:
            job.result()
    if source != sources(bundle):
        raise ValueError("a frozen source changed during replay")
    save_json(work / "run-receipt.json", dict(wall_s=perf_counter() - started))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--bundle", type=Path, default=BUNDLE)
    cli.add_argument("--work", type=Path, required=True)
    args = cli.parse_args()
    run(args.bundle, args.work)


if __name__ == "__main__":
    main()
