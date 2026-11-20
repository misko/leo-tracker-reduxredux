"""Launch slim direct v5 on supplied factor and archive paths, with capped-service receipts."""

import argparse
import importlib.util
import json
import os
import resource
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path
from time import perf_counter

ENTRY = "tools.pipeline_eval.variants.v5_direct_lifetime"
MEMORY = 512 * 1024**2


def explicit_arguments(
    *,
    native,
    native_sha256,
    track_config,
    config_sha256,
    session,
    archive,
    native_backend,
    library,
    tile,
    screen_center,
    width_km=25,
):
    options = {
        "native": native,
        "native-sha256": native_sha256,
        "track-config": track_config,
        "config-sha256": config_sha256,
        "session": session,
        "archive": archive,
        "native-backend": native_backend,
        "library": library,
        "width-km": width_km,
    }
    return [
        *(a for k, v in options.items() for a in (f"--{k}", str(v))),
        "--tile",
        *map(str, tile),
        "--screen-center",
        *map(str, screen_center),
    ]


def sample(cpu):
    entry = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    group = Path("/sys/fs/cgroup") / entry.lstrip("/")
    limits = {
        k: int((group / k).read_text())
        for k in (
            "memory.max",
            "memory.swap.max",
            "memory.current",
            "memory.peak",
            "memory.swap.current",
        )
    }
    counters = {}
    for file, names in (("cpu.stat", ("usage_usec",)), ("memory.events", ("oom", "oom_kill"))):
        values = dict(line.split() for line in (group / file).read_text().splitlines())
        counters.update({f"{file}.{k}": int(values[k]) for k in names})
    if (
        limits["memory.max"] != MEMORY
        or limits["memory.swap.max"] != 0
        or (os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10)
    ):
        raise ValueError(
            "direct whole receiver did not inherit the capped service and position pin"
        )
    return dict(
        limits,
        **counters,
        pid=os.getpid(),
        cpus=[cpu],
        cgroup=entry,
        monotonic_s=perf_counter(),
        rss_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )


def observed_run(bundle, result, stages, cpu, flags):
    module = importlib.util.find_spec(ENTRY)
    if module is None or not Path(module.origin).resolve().is_relative_to(bundle.resolve()):
        raise ValueError("standalone position module is outside its declared bundle")
    if any(p.resolve().is_relative_to("/mnt/qnap01") for p in (result, stages)):
        raise ValueError("QNAP is read-only")
    start = sample(cpu)
    with stages.open("x") as receipt:
        json.dump(dict(start=start), receipt, allow_nan=False)
    print("stage: direct position enter", flush=True)
    original, sys.argv = sys.argv, [ENTRY, *flags]
    try:
        with result.open("x") as output, redirect_stdout(output):
            runpy.run_module(ENTRY, run_name="__main__", alter_sys=True)
    finally:
        sys.argv = original
    end = sample(cpu)
    forbidden = (
        "tools.pipeline_eval.qualification",
        "tools.pipeline_eval.__main__",
        "evaluate_algo07",
        "evaluate_accuracy_repair",
    )
    evaluator = sorted(n for n in sys.modules if n.startswith(forbidden))
    if evaluator:
        raise ValueError("qualification unexpectedly entered the numerical position process")
    temp = stages.with_suffix(".partial")
    with temp.open("x") as receipt:
        json.dump(
            dict(start=start, end=end, entry=module.origin, evaluator_modules=evaluator),
            receipt,
            allow_nan=False,
        )
    temp.replace(stages)
    print("stage: direct position complete", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("stages", type=Path)
    parser.add_argument("cpu", type=int)
    prepare, remaining = parser.parse_known_args()
    observed_run(prepare.bundle, prepare.result, prepare.stages, prepare.cpu, remaining)


if __name__ == "__main__":
    main()
