"""Stage-bounded compact-v5 transfer over the existing arbitrary-input port."""

import argparse
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..__main__ import save_json
from ..variants import transfer_budget as rule
from . import compact_transfer as compact
from . import transfer_budget_scenes as scenes
from .fresh_scenes import _read, _sha

REPORT = compact.REPORT.parents[1] / "deployment/transfer-budget"
WORKER = Path(__file__).with_name("transfer_budget_worker.py")
CPUS = (13, 14, 15, 16)
METHODS = {
    "diagnostic": "compact_precovery_trace",
    "gate": "v5_secant_transfer_budget",
    "control": "v5_secant_transfer_stock",
}
TIMEOUT_S = 145


def run_one(job, kernel, cpu, mode, timeout=225):
    row, data, objects = job
    cmd = compact.worker_command(
        cpu, objects, kernel, WORKER, modules=(compact.v5_secant_fit, rule)
    )
    package = Path(compact.v5_secant_fit.__file__).parent.parent
    for name in ("__main__.py", "scoring.py", "corpus.py"):
        cmd[-4:-4] = ("--ro-bind", str(package / name), f"/worker/tools/pipeline_eval/{name}")
    stdout, stderr, status, elapsed = compact.invoke(
        ["nice", "-n", "10", *cmd, mode], data, timeout
    )
    trace, errors = [], []
    for line in stderr.decode(errors="replace").splitlines():
        if line.startswith("{"):
            trace.append(json.loads(line))
        else:
            errors.append(line)
    if status == "complete":
        result = json.loads(stdout)
    else:
        reason = (
            f"worker deadline {timeout} s" if status == "timed_out" else "\n".join(errors[-10:])
        )
        result = compact.portable_v5.unavailable(reason) | {"status": status}
    compact.validate_result(result)
    print(cpu, mode, row["id"], result["status"], round(elapsed, 1), flush=True)
    return dict(row, method=METHODS[mode], result=result, trace=trace, wall_s=elapsed, cpu=cpu)


def diagnose(panel, scratch):
    scratch.mkdir(parents=True, exist_ok=True)
    lanes, _ = compact.prepare(panel)
    kernel = scratch / "projector.so"
    compact.orbit_projector.compile_kernel(kernel)
    jobs = [*lanes[0], *lanes[1]]
    source = dict(
        worker_sha256=_sha(WORKER),
        compact_optimizer_sha256=_sha(Path(compact.v5_secant_fit.__file__)),
        cases=[group[0]["id"] for group in jobs],
    )
    save_json(scratch / "source-lock.json", source)
    with ThreadPoolExecutor(max_workers=4) as pool:
        out = [
            pool.submit(run_one, job, kernel, CPUS[i % 4], "diagnostic", 150)
            for i, job in enumerate(jobs)
        ]
        rows = [r.result() for r in out]
    save_json(scratch / "diagnostics.json", rows)


def qualify(panel, scratch, output):
    scratch.mkdir(parents=True, exist_ok=True)
    assert not (output / "prediction-lock.json").exists()
    modules = (
        Path(__file__),
        WORKER,
        Path(scenes.__file__),
        Path(rule.__file__),
        Path(compact.__file__),
        Path(compact.v5_secant_fit.__file__),
        Path(scenes.inputs.__file__),
        Path(scenes.inputs.cold.__file__),
        Path(scenes.inputs.empirical.__file__),
        output / "PROTOCOL.md",
    )
    lock = compact.portable.source_lock() | {str(p): _sha(p) for p in modules}
    lock["development_prediction_lock"] = _sha(compact.REPORT / "prediction-lock.json")
    save_json(output / "policy-lock.json", lock)
    scenes.generate(scratch, secrets.token_bytes(32))
    fresh, inventory = scenes.jobs(scratch)
    lanes, _ = compact.prepare(panel)
    development = [*lanes[0], *lanes[1]]
    jobs = [(job, mode, "fresh") for job in fresh for mode in ("gate", "control")]
    jobs.extend((job, "gate", "development") for job in development)
    matrix = [dict(job[0], method=METHODS[mode], cohort=cohort) for job, mode, cohort in jobs]
    save_json(output / "requests.json", matrix)
    save_json(output / "fresh-history.json", inventory)
    names = ("public/cases.json", "public/native.json", "private/truth.json", "private/seed.bin")
    commitment = {name: _sha(scratch / name) for name in names}
    save_json(output / "fresh-input-lock.json", commitment)
    kernel = scratch / "projector.so"
    compact.orbit_projector.compile_kernel(kernel)

    def work(cpu, batch):
        return [
            dict(run_one(job, kernel, cpu, mode, TIMEOUT_S), cohort=cohort)
            for job, mode, cohort in batch
        ]

    with ThreadPoolExecutor(max_workers=4) as pool:
        lanes = [pool.submit(work, cpu, jobs[i::4]) for i, cpu in enumerate(CPUS)]
        results = [item for lane in lanes for item in lane.result()]
    file = output / "predictions.json"
    save_json(file, results)
    if any(_sha(scratch / name) != digest for name, digest in commitment.items()):
        raise ValueError("fresh observation or target bytes changed after lock")
    evidence = (
        file.name,
        "policy-lock.json",
        "requests.json",
        "fresh-input-lock.json",
        "fresh-history.json",
    )
    save_json(output / "prediction-lock.json", {name: _sha(output / name) for name in evidence})
    save_json(output / "released-truth.json", _read(scratch / "private/truth.json"))
    save_json(
        output / "released-seed.json",
        dict(seed_hex=(scratch / "private/seed.bin").read_bytes().hex()),
    )
    save_json(output / "fresh-draw.json", _read(scratch / "public/cases.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel", type=Path)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--qualify", type=Path)
    opts = parser.parse_args()
    if not set(CPUS) <= os.sched_getaffinity(0):
        parser.error("diagnostics require the scheduled core set")
    if opts.qualify:
        qualify(opts.panel, opts.scratch, opts.qualify)
    else:
        diagnose(opts.panel, opts.scratch)
