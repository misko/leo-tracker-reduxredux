"""Qualify staged direct compact v5 inside a true Linux 512 MiB service."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep, time_ns
from uuid import uuid4

REPORT = Path("reports/2026_11_19_receiver_screening/streamlined/direct-cavity-cap")
ROSTER = {"ordinary-DS26-0036": 4, "ordinary-DS29-0082": 5}
MEMORY, LIMIT = 512 * 1024**2, 165
DIRECT, BOUNDED = "v5_direct_cavity", "v5_direct_cavity_cap"
STAGES = frozenset(
    (
        ("localization_v3.py", "prepare_native_scan"),
        ("v5_core.py", "initial_selection"),
        ("conservative_recovery.py", "conservative_recovery"),
        ("history_policy.py", "history_policy"),
        ("signed_context.py", "signed_context"),
        ("family_cavity.py", "nominate_families"),
        ("family_cavity.py", "cavity_policy"),
    )
)


def counters(path):
    return {k: int(v) for k, v in map(str.split, path.read_text().splitlines())}


def sample(group):
    try:
        fields = (
            "memory.current",
            "memory.peak",
            "memory.swap.current",
            "memory.max",
            "memory.swap.max",
        )
        return {k: int((group / k).read_text()) for k in fields} | {
            "cpu_s": counters(group / "cpu.stat")["usage_usec"] / 1e6,
            "events": counters(group / "memory.events"),
        }
    except FileNotFoundError:
        return None


def observed_worker(unit, cpu, flags):
    path = next(
        r[3:] for r in Path("/proc/self/cgroup").read_text().splitlines() if r.startswith("0::")
    )
    group = Path("/sys/fs/cgroup") / path.lstrip("/")
    state = sample(group)
    if (
        group.name != unit + ".service"
        or state["memory.max"] != MEMORY
        or state["memory.swap.max"] != 0
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
    ):
        raise ValueError("requested capped service and pin were not acquired")
    print(
        "cap " + json.dumps(dict(state, cpu=cpu, nice=os.nice(0), group=path)),
        file=sys.stderr,
        flush=True,
    )
    observed = set()
    monitoring = sys.monitoring
    event = monitoring.events.PY_START

    def stage(code, _offset):
        key = code.co_filename.rsplit("/", 1)[-1], code.co_name
        if key in STAGES and key not in observed:
            observed.add(key)
            print(
                "stage " + json.dumps(dict(sample(group), name=key[1])), file=sys.stderr, flush=True
            )
        return monitoring.DISABLE

    monitoring.use_tool_id(2, "direct cavity cap stage sampler")
    monitoring.register_callback(2, event, stage)
    monitoring.set_events(2, event)
    try:
        from tools.pipeline_eval.variants.v5_direct_cavity import main

        sys.argv = [sys.argv[0], *flags]
        main()
    finally:
        monitoring.set_events(2, 0)
        monitoring.register_callback(2, event, None)
        monitoring.free_tool_id(2)


def systemd_fields(unit):
    keys = ("ControlGroup", "Result", "MemoryPeak", "CPUUsageNSec", "ExecMainStatus")
    record = subprocess.run(
        ["systemctl", "--user", "show", unit, *(f"-p{k}" for k in keys)],
        capture_output=True,
        text=True,
        check=False,
        timeout=4,
    )
    return dict(line.split("=", 1) for line in record.stdout.splitlines() if "=" in line)


def source(trial):
    paths = (Path(__file__).resolve(), trial.common.ROOT / REPORT / "PROTOCOL.md")
    old = trial.common.seal(trial.REPORT, "receipt.json", ("bundle.json", "positions.jsonl.gz"))
    return dict(
        prior=old, files={str(p.relative_to(trial.common.ROOT)): trial.common.sha(p) for p in paths}
    )


def lock(trial, work, original):
    work.mkdir(exist_ok=False, parents=True)
    manifest = original / "bundle.json"
    frozen = source(trial)
    if trial.common.sha(manifest) != frozen["prior"]["files"]["bundle.json"]:
        raise ValueError("staged direct bundle differs from the sealed qualification")
    inputs = {key: trial.input_case(key)[2] for key in ROSTER}
    old = trial.common.read(original / "plan.json")
    if any(tags != old["bindings"][key] for key, tags in inputs.items()):
        raise ValueError("direct qualification used different inputs")
    trial.save_json(
        work / "plan.json",
        dict(
            source=frozen,
            inputs=inputs,
            pins=ROSTER,
            memory_max=MEMORY,
            swap_max=0,
            limit_s=LIMIT,
            attempts=4,
            bundle_sha256=trial.common.sha(manifest),
            sealed_ns=time_ns(),
        ),
    )


def replay(trial, work, original, key, method):
    plan = trial.common.read(work / "plan.json")
    if plan["source"] != source(trial):
        raise ValueError("capped qualifier source changed")
    cpu = plan["pins"][key]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10:
        raise ValueError("start the supervisor on the recorded pin and at nice 10")
    alt = method == BOUNDED
    authorization = trial.common.read(work / "bounded-lock.json") if alt else plan
    bundle_path = work / "bounded-bundle.json" if alt else original / "bundle.json"
    if trial.common.sha(bundle_path) != authorization["bundle_sha256"]:
        raise ValueError("science release manifest differs from its lock")
    bundle = work / "bounded" if alt else original / trial.RELEASE
    ledger = trial.common.read(bundle_path)
    if any(trial.common.sha(bundle / p) != digest for p, digest in ledger["files"].items()):
        raise ValueError("staged source file differs from its declared digest")
    if trial.common.sha(bundle / "native/native_bound.so") != ledger["binary"]:
        raise ValueError("staged native numerical binary changed")
    case, request, binding = trial.input_case(key)
    if binding != plan["inputs"][key]:
        raise ValueError("frozen inputs changed")
    out = work / "runs" / key / method
    out.mkdir(parents=True, exist_ok=False)
    library = out / "orbit_projector.so"
    trial.orbit_projector.compile_kernel(library)
    unit = "leo-direct-cavity-cap-" + uuid4().hex[:10]
    group = None
    cli = trial.direct_command(case, request["job"], bundle, library)
    args = [
        "systemd-run",
        "--user",
        "--pipe",
        "--wait",
        f"--unit={unit}",
        f"--working-directory={bundle}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=MemoryAccounting=yes",
        "--property=CPUAccounting=yes",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--setenv=PYTHONPATH={bundle}",
        "--setenv=PYTHONNOUSERSITE=1",
        *(
            f"--setenv={key}=1"
            for key in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "BLIS_NUM_THREADS",
            )
        ),
        "/usr/bin/taskset",
        "-c",
        str(cpu),
        cli[0],
        "-B",
        str(Path(__file__).resolve()),
        "worker",
        unit,
        str(cpu),
        *cli[4:],
    ]
    live, start = [], monotonic()
    result_path, log_path = out / "result.json", out / "service.log"
    with result_path.open("xb") as dst, log_path.open("xb") as log:
        proc = subprocess.Popen(args, stdout=dst, stderr=log, cwd=bundle)
        while proc.poll() is None and monotonic() - start <= LIMIT + 5:
            group = group or systemd_fields(unit).get("ControlGroup")
            if group and (state := sample(Path("/sys/fs/cgroup") / group.lstrip("/"))):
                live.append(dict(state, wall_s=monotonic() - start))
            sleep(0.4)
        if proc.poll() is None:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=4)
        proc.wait(timeout=4)
    wall = monotonic() - start
    terminal = systemd_fields(unit)
    log = log_path.read_text(errors="replace")
    stages = [json.loads(row[6:]) for row in log.splitlines() if row.startswith("stage ")]
    proofs = [json.loads(row[4:]) for row in log.splitlines() if row.startswith("cap ")]
    claimed = re.search(r"Finished with result: (\S+)", log)
    service_status = claimed[1] if claimed else terminal.get("Result")
    status, reason = {
        "oom-kill": ("failed", "Kernel OOM kill at 512 MiB"),
        "timeout": ("timed_out", "165 second capped service deadline"),
    }.get(service_status, ("failed", f"Service ended with {service_status}"))
    result = (
        trial.common.read(result_path)
        if proc.returncode == 0 and result_path.stat().st_size
        else trial.v5_lean._no_fix(reason, status=status)
    )
    trial.validate_result(result)
    row = dict(
        binding,
        method=method,
        cpu=cpu,
        wall_s=wall,
        service_result=service_status,
        kernel=terminal,
        proof=proofs,
        live=live,
        stages=stages,
        result=result,
        returncode=proc.returncode,
        log_sha256=trial.common.sha(log_path),
        source_lock_sha256=trial.common.sha(work / "plan.json"),
        bundle_sha256=authorization["bundle_sha256"],
    )
    trial.save_json(out / "measurement.json", row)
    print(key, method, result["status"], service_status, round(wall, 2), flush=True)


def main():
    from tools.pipeline_eval.qualification import direct_cavity_trial as trial

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("original", type=Path)
    p.add_argument("mode", choices=("lock", "run"))
    p.add_argument("key", nargs="?", choices=ROSTER)
    p.add_argument("method", nargs="?", choices=(DIRECT, BOUNDED))
    a = p.parse_args()
    work, original = trial.local_output(a.work), a.original.resolve()
    if a.mode == "lock":
        lock(trial, work, original)
    else:
        replay(trial, work, original, a.key, a.method)


if __name__ == "__main__":
    if sys.argv[1] == "worker":
        observed_worker(sys.argv[2], int(sys.argv[3]), sys.argv[4:])
    else:
        main()
