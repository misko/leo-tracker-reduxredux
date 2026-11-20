"""Run the staged direct lifetime receiver in a kernel-capped service."""

import argparse
import json
import os
import re
import resource
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep, time_ns
from uuid import uuid4

PINS = {"ordinary-DS26-0036": 4, "ordinary-DS29-0082": 5}
MEMORY, LIMIT = 512 * 1024**2, 165
TMP = Path("/srv/bulk/leo-dev/dlt-tmp")
STAGES = {
    "prepare_native_scan",
    "initial_selection",
    "conservative_recovery",
    "history_policy",
    "signed_context",
    "nominate_families",
    "cavity_policy",
}


def observe(unit, cpu, bundle, flags):
    entry = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    group = Path("/sys/fs/cgroup") / entry.lstrip("/")

    def read(name):
        return int((group / name).read_text())

    if (
        group.name != unit + ".service"
        or read("memory.max") != MEMORY
        or read("memory.swap.max") != 0
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
        or Path(os.environ["TMPDIR"]) != TMP
    ):
        raise ValueError("measured worker lacks its physical cap, pin or scratch settings")

    def emit(kind, value):
        print(kind + " " + json.dumps(value), file=sys.stderr, flush=True)

    emit(
        "proof",
        dict(
            cgroup=entry,
            cpu=cpu,
            nice=os.nice(0),
            memory=MEMORY,
            swap=0,
            tmpdir=os.environ["TMPDIR"],
        ),
    )
    start, entered, paths, code_counts = monotonic(), set(), set(), {}
    monitor = sys.monitoring
    event = monitor.events.PY_START
    prefix = str(bundle) + "/"

    def reached(code, _offset):
        name = code.co_filename
        if name.startswith(prefix) or name == "<native-bound-original-boundaries>":
            rel = name.removeprefix(prefix)
            code_counts[rel] = code_counts.get(rel, 0) + 1
            if rel not in paths:
                paths.add(rel)
                emit("reached", rel)
            stage = code.co_name
            if stage in STAGES and stage not in entered:
                entered.add(stage)
                emit(
                    "stage",
                    dict(
                        name=stage,
                        wall_s=monotonic() - start,
                        charge=read("memory.current"),
                        peak=read("memory.peak"),
                    ),
                )
        return monitor.DISABLE

    monitor.use_tool_id(2, "capped direct path and stage observer")
    monitor.register_callback(2, event, reached)
    monitor.set_events(2, event)
    try:
        from tools.pipeline_eval.variants.v5_direct_lifetime import main

        sys.argv = [sys.argv[0], *flags]
        main()
    finally:
        monitor.set_events(2, 0)
        monitor.register_callback(2, event, None)
        monitor.free_tool_id(2)
        evaluator = (
            "evaluate_algo07",
            "evaluate_accuracy_repair",
            "tools.pipeline_eval.__main__",
            "tools.pipeline_eval.qualification",
        )
        stat = dict(line.split() for line in (group / "cpu.stat").read_text().splitlines())
        emit(
            "finish",
            dict(
                paths=len(paths),
                execution_locations=sum(code_counts.values()),
                code_counts=code_counts,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                cgroup_peak=read("memory.peak"),
                cgroup_cpu_s=int(stat["usage_usec"]) * 1e-6,
                eval_modules=sorted(n for n in sys.modules if n.startswith(evaluator)),
            ),
        )


def source(direct, build):
    recipe = (
        Path(__file__).resolve(),
        Path(build.__file__),
        build.REPORT / "PROTOCOL.md",
        direct.common.ROOT / build.GLUE,
    )
    return {str(p.relative_to(build.ROOT)): direct.common.sha(p) for p in recipe}


def lock(direct, build, work):
    manifest = direct.common.read(work / "bundle.json")
    candidate = work / "plan.json"
    if candidate.exists() or manifest["altered"][build.GLUE]["after"] != direct.common.sha(
        build.ROOT / build.GLUE
    ):
        raise ValueError("source lock requires the staged and unrun release")
    proof = {key: direct.input_case(key)[2] for key in PINS}
    base = direct.common.seal(direct.REPORT, "receipt.json", ("positions.jsonl.gz",))
    direct.save_json(
        candidate,
        dict(
            cases=PINS,
            inputs=proof,
            source=source(direct, build),
            frozen_ns=time_ns(),
            memory=MEMORY,
            swap=0,
            nice=10,
            service_limit_s=LIMIT,
            tmpdir=str(TMP),
            bundle_sha256=direct.common.sha(work / "bundle.json"),
            unrestricted_direct=base,
        ),
    )


def replay(direct, build, cap, work, key):
    cpu = PINS[key]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10 or Path(os.environ["TMPDIR"]) != TMP:
        raise ValueError("incorrect supervisor pin, priority or disk scratch")
    plan_path, ledger_path = work / "plan.json", work / "bundle.json"
    plan, ledger = (direct.common.read(p) for p in (plan_path, ledger_path))
    if (
        plan["source"] != source(direct, build)
        or direct.common.sha(ledger_path) != plan["bundle_sha256"]
    ):
        raise ValueError("scientific release or trial source changed")
    bundle = work / direct.RELEASE
    if any(direct.common.sha(bundle / p) != d for p, d in ledger["files"].items()):
        raise ValueError("scientific release file changed")
    if direct.common.sha(bundle / "native/native_bound.so") != ledger["binary"]:
        raise ValueError("rebuilt numerical bound changed")
    case, request, binding = direct.input_case(key)
    if binding != plan["inputs"][key]:
        raise ValueError("native factors or causal authority changed")
    out = work / "runs" / key
    out.mkdir(parents=True, exist_ok=False)
    library = out / "projection.so"
    direct.orbit_projector.compile_kernel(library)
    unit = "leo-dlt-" + uuid4().hex[:10]
    cli = direct.direct_command(case, request["job"], bundle, library)
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={bundle}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=MemoryAccounting=yes",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--setenv=PYTHONPATH={bundle}",
        f"--setenv=TMPDIR={TMP}",
        "--setenv=PYTHONNOUSERSITE=1",
        *(
            f"--setenv={v}=1"
            for v in (
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
        "observe",
        unit,
        str(cpu),
        str(bundle),
        *cli[4:],
    ]
    r, log = out / "result.json", out / "service.log"
    live, start, path = [], monotonic(), None
    with r.open("xb") as result, log.open("xb") as lines:
        proc = subprocess.Popen(command, stdout=result, stderr=lines, cwd=bundle)
        while proc.poll() is None and monotonic() - start < LIMIT + 5:
            path = path or cap.systemd_fields(unit).get("ControlGroup")
            if path and (state := cap.sample(Path("/sys/fs/cgroup") / path.lstrip("/"))):
                live.append(dict(state, wall_s=monotonic() - start))
            sleep(0.5)
        if proc.poll() is None:
            subprocess.run(["systemctl", "--user", "stop", unit], timeout=4, check=False)
        proc.wait(timeout=4)
    wall = monotonic() - start
    terminal = cap.systemd_fields(unit)
    raw_log = log.read_text(errors="replace")
    claim = re.search(r"Finished with result: (\S+)", raw_log)
    status = terminal.get("Result") or (claim[1] if claim else None)
    samples = {prefix: [] for prefix in ("proof", "reached", "stage", "finish")}
    for line in raw_log.splitlines():
        label, _, value = line.partition(" ")
        if label in samples:
            samples[label].append(json.loads(value))
    if proc.returncode == 0 and status == "success" and r.stat().st_size:
        result = direct.common.read(r)
    else:
        result = direct.v5_lean._no_fix(
            f"512 MiB service ended with {status}",
            status="timed_out" if status == "timeout" else "failed",
        )
    direct.validate_result(result)
    row = dict(
        binding,
        method="v5_direct_lifetime",
        cpu=cpu,
        source_lock_sha256=direct.common.sha(plan_path),
        bundle_sha256=plan["bundle_sha256"],
        result=result,
        wall_s=wall,
        cgroup=terminal,
        service_result=status,
        returncode=proc.returncode,
        live=live,
        observations=samples,
        log_sha256=direct.common.sha(log),
    )
    direct.save_json(out / "attempt.json", row)
    print(key, result["status"], status, round(wall, 3), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "observe":
        observe(sys.argv[2], int(sys.argv[3]), Path(sys.argv[4]), sys.argv[5:])
    else:
        from tools.pipeline_eval.qualification import direct_cavity_cap as cap
        from tools.pipeline_eval.qualification import direct_cavity_trial as direct
        from tools.pipeline_eval.qualification import direct_lifetime_bundle as build

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("work", type=Path)
        parser.add_argument("action", choices=("lock", "run"))
        parser.add_argument("key", nargs="?", choices=PINS)
        args = parser.parse_args()
        root = direct.local_output(args.work)
        if args.action == "lock":
            lock(direct, build, root)
        else:
            replay(direct, build, cap, root, args.key)
