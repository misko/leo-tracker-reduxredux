"""Run the original four-config worker on the eight previously frozen DS29 recordings."""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLIND = HERE.parent / "2026_11_18_blind_regional_receiver"
ARCHIVE = Path("/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001")
DS29_PLAN = Path.home() / ".cache/accuracy-repair-20261115/one-track-plan.json"
OUTPUT = Path("/srv/bulk/leo-dev/blind-v5-comparison-20261118/ds29")
ROLES = ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks")


def read(path):
    return json.loads(path.read_bytes())


def published_worker():
    sys.path.insert(0, str(ARCHIVE / "runner/tools"))
    import evaluate_accuracy_repair as original
    return original


def manifest():
    original = read(ARCHIVE / "plans/science.json")
    ds29 = read(DS29_PLAN)
    if any(original[k] != ds29[k] for k in ("source", "native_manifest", "python")):
        raise ValueError("archived DS29 data refer to a different numerical runtime")
    return dict(original, output=str(OUTPUT), cohorts={"DS29": ds29["cohorts"]["DS29"]})


def lane(item):
    i, cpu, case, deadline = item
    runner, cfg = published_worker(), manifest()
    assignment = dict(case=case, dataset="DS29", repetition=0)
    env = dict(runner.ENVIRONMENT, PYTHONPATH=cfg["source"]["root"] + ":" +
               str(Path(cfg["worker"]).parent))
    order = ROLES[i % len(ROLES):] + ROLES[:i % len(ROLES)]
    for role in order:
        dest = OUTPUT / (case + "-r0") / role
        finished = dest.parent / (role + "-execution.json")
        if finished.is_file():
            runner.validate_record(cfg, assignment, role, read(finished))
            continue
        timeout = min(cfg["timeout_seconds"], deadline - time.monotonic())
        if timeout < 1:
            print(case, role, "not started by overall time limit", flush=True)
            break
        req = runner.worker_request(cfg, assignment, role)
        if req["job"]["evaluation_reference"] is not None:
            raise ValueError("scoring-only coordinates in worker request")
        dest.mkdir(parents=True, exist_ok=False)
        req_file = dest / "experimental-request.json"
        runner.write(req_file, req)
        cmd = ["taskset", "-c", str(cpu), cfg["python"], "-B", cfg["worker"],
               "worker", "--request", str(req_file)]
        print(case, role, "started", flush=True)
        proc = runner.supervise_worker(cmd, dest / "worker.log", timeout, env)
        status = proc["status"]
        if status != "timed_out":
            produced = (dest / "worker-result.json").is_file()
            status = "complete" if proc["returncode"] == 0 and produced else "failed"
        rec = dict(role=role, status=status, request_sha256=runner.ev.digest(req), process=proc,
                   command=cmd, timeout_seconds=timeout)
        if status == "complete":
            rec["worker"] = read(dest / "worker-result.json")
        runner.write(finished, rec)
        runner.validate_record(cfg, assignment, role, rec)
        print(case, role, status, round(proc["wall_seconds"], 1), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=45)
    args = parser.parse_args()
    runner = published_worker()
    runner.check_bindings(read(ARCHIVE / "plans/science.json"))
    ds29 = manifest()["cohorts"]["DS29"]
    selected = read(BLIND / "recorded_private/selection.json")["chosen"]
    by_case = {r["dataset_label"]: r for r in ds29["members"]}
    cases = []
    for item in selected:
        case = item["member"]["dataset_label"]
        if by_case[case]["input_sha256"] != item["source"]["input_sha256"]:
            raise ValueError(f"native input mismatch for {case}")
        cases.append(case)
    assert len(set(cases)) == 8
    cpus = sorted(os.sched_getaffinity(0))
    deadline = time.monotonic() + 60 * args.minutes
    with ProcessPoolExecutor(max_workers=min(len(cpus), len(cases))) as pool:
        list(pool.map(lane, [(i, cpus[i % len(cpus)], case, deadline)
                             for i, case in enumerate(sorted(cases))]))


if __name__ == "__main__":
    main()
