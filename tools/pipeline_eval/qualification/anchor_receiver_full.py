"""Run one predeclared full native anchor replay with the exact previous offers."""

import argparse
import json
import os
import subprocess
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, validate_result
from ..variants import anchor_receiver_orbits
from . import anchor_receiver_trial as prepared
from . import native_joint_full as old
from .anchor_receiver_full_worker import BOUNDARY
from .fresh_scenes import _read, _sha

REPORT = prepared.REPORT.with_name("anchor-full")
METHOD = "native_anchor_receiver"
CPUS = (2, 3, 6, 10, 11)
WALL_CAP_S = 720
WORKER = Path(__file__).with_name("anchor_receiver_full_worker.py")
STOCK = old.REPORT
SOURCE = Path(anchor_receiver_orbits.__file__)


def sources(bundle):
    historical = old.base.sources(bundle)
    small = _read(prepared.REPORT / "source-lock.json")
    relative = str(SOURCE.relative_to(prepared.ROOT))
    if small["files"][relative] != _sha(SOURCE):
        raise ValueError("anchor numerical source differs from the prepared trial")
    return dict(
        stream=historical,
        fitter_sha256=_sha(SOURCE),
        prepared_source_lock_sha256=_sha(prepared.REPORT / "source-lock.json"),
        wrapper_sha256=_sha(WORKER),
        runner_sha256=_sha(Path(__file__)),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
    )


def prepare(bundle):
    stock, jobs = old.prepare(bundle)
    receipt = STOCK / "prediction-lock.json"
    old.base.secant_full._verify_files(STOCK, _read(receipt)["files"])
    if _read(STOCK / "plan.json")["cases"] != stock["cases"]:
        raise ValueError("full anchor roster must match archived native stock")
    return dict(
        stock,
        source=sources(bundle),
        cpus=list(CPUS),
        wall_cap_s=WALL_CAP_S,
        stock_prediction_lock_sha256=_sha(receipt),
    ), jobs


def command(cpu, paths, bundle):
    argv = old.base.native.command(cpu, paths, source=bundle)
    argv[argv.index(str(bundle / "main.py"))] = str(WORKER)
    for source, name in (
        (bundle / "main.py", "native_lean.py"),
        (SOURCE, "anchor_receiver_orbits.py"),
    ):
        argv[-3:-3] = [
            "--ro-bind",
            str(source),
            f"/worker/tools/pipeline_eval/variants/{name}",
        ]
    return argv


def attempt(query, paths, cpu, bundle):
    packet = query["packet"]
    raw = encoded(packet)
    started = perf_counter()
    try:
        worker = subprocess.run(
            command(cpu, paths, bundle),
            input=raw,
            capture_output=True,
            timeout=old.base.CAP,
            check=True,
        )
        outcome = json.loads(worker.stdout)
    except (ValueError, OSError, subprocess.SubprocessError) as err:
        reason = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
        outcome = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=reason or str(err),
                boundary=BOUNDARY,
                metrics={},
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            )
        )
    validate_result(outcome["result"])
    row = {k: v for k, v in query.items() if k != "packet"}
    row.update(
        outcome,
        method=METHOD,
        cpu=cpu,
        worker_wall_s=perf_counter() - started,
        input_sha256=old.base.phase.corpus._sha(raw),
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        tile=packet["offer"],
    )
    print(row["id"], row["result"]["status"], round(row["worker_wall_s"], 2), flush=True)
    return row


def run(work, bundle, output):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("use CPUs 2, 3, 6, 10 and 11")
    work = local_output(work)
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    plan, jobs = prepare(bundle)
    save_json(work / "plan.json", plan)
    save_json(output / "roster.json", plan)
    journal = work / "predictions"
    journal.mkdir()
    remaining, guard = deque(jobs), Lock()

    def lane(cpu):
        while perf_counter() - start < WALL_CAP_S - old.base.CAP - 10:
            with guard:
                if not remaining:
                    return
                row, paths = remaining.popleft()
            save_json(journal / f"{row['id']}.json", attempt(row, paths, cpu, bundle))

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, CPUS))
    if sources(bundle) != plan["source"]:
        raise ValueError("full anchor source changed during inference")
    rows = [_read(path) for path in journal.glob("*.json")]
    save_json(
        work / "run-receipt.json",
        dict(
            wall_s=perf_counter() - start,
            attempted=len(rows),
            scheduled=len(jobs),
            statuses=dict(Counter(r["result"]["status"] for r in rows)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=old.base.BUNDLE)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    run(args.work, args.bundle, args.output)
