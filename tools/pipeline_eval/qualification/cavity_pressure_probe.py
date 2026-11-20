"""Trace standalone compact stages with a small persistent in-service observer."""

import json
import os
import resource
import runpy
import subprocess
import sys
from pathlib import Path
from time import monotonic

MEMORY = 512 * 1024**2
OBSERVER = 24 * 1024**2
STAGES = frozenset(
    (
        ("localization_v3.py", "prepare_native_scan"),
        ("localization_v3_engine.py", "_prepared_values"),
        ("localization_v3_inputs.py", "prepare_initial_sky"),
        ("localization_v3_inputs.py", "prepare_phase_history"),
        ("tracks.py", "prepare_tracks"),
        ("v5_core.py", "scan_context"),
        ("v5_core.py", "ranked_initial_nodes"),
        ("v5_core.py", "fit_initial_nodes"),
        ("conservative_recovery.py", "conservative_recovery"),
        ("conservative_recovery.py", "salvage"),
        ("history_policy.py", "history_policy"),
        ("family_weighting.py", "confidence_for"),
        ("signed_context.py", "signed_context"),
        ("family_cavity.py", "nominate_families"),
        ("family_cavity.py", "family_data"),
        ("family_cavity.py", "cavity_policy"),
        ("event_position.py", "refit"),
    )
)


def group():
    entry = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    return Path("/sys/fs/cgroup") / entry.lstrip("/")


def values(path, keys):
    raw = dict(line.split() for line in path.read_text().splitlines())
    return {k: int(raw[k]) for k in keys}


def kernel(path):
    fields = (
        "memory.current",
        "memory.peak",
        "memory.swap.current",
        "memory.max",
        "memory.swap.max",
    )
    return {k: int((path / k).read_text()) for k in fields} | {
        "parts": values(path / "memory.stat", ("anon", "file", "kernel")),
        "events": values(path / "memory.events", ("oom", "oom_kill", "max")),
        "cpu_s": values(path / "cpu.stat", ("usage_usec",))["usage_usec"] * 1e-6,
    }


def emit(tag, row):
    print(tag + " " + json.dumps(row, separators=(",", ":")), file=sys.stderr, flush=True)


def trace(root, flags):
    path = group()
    monitor = sys.monitoring
    events = monitor.events
    names = {}

    def record(code, event):
        emit(
            "stage", dict(kernel(path), operation=names[code], event=event, monotonic_s=monotonic())
        )

    def seen(code, _offset):
        filename = Path(code.co_filename)
        key = filename.name, code.co_name
        if filename.is_relative_to(root) and key in STAGES:
            names[code] = "/".join(key)
            monitor.set_local_events(2, code, events.PY_RETURN)
            record(code, "start")
            return None
        return monitor.DISABLE

    def returned(code, _offset, _value):
        record(code, "return")

    monitor.use_tool_id(2, "compact pressure sampler")
    monitor.register_callback(2, events.PY_START, seen)
    monitor.register_callback(2, events.PY_RETURN, returned)
    monitor.set_events(2, events.PY_START)
    sys.argv = [str(root), *flags]
    try:
        runpy.run_path(str(root), run_name="__main__")
    finally:
        monitor.set_events(2, 0)
        for code in names:
            monitor.set_local_events(2, code, 0)
        for event in (events.PY_START, events.PY_RETURN):
            monitor.register_callback(2, event, None)
        monitor.free_tool_id(2)
        emit(
            "finish",
            dict(
                kernel(path),
                rss_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                evaluator=[
                    n
                    for n in sys.modules
                    if n.startswith(
                        ("tools.pipeline_eval.qualification", "evaluate_accuracy_repair")
                    )
                ],
            ),
        )


def observe(root, cpu, flags):
    path = group()
    initial = kernel(path)
    if (
        initial["memory.max"] != MEMORY
        or initial["memory.swap.max"] != 0
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
    ):
        raise ValueError("pressure observer is outside its declared physical cap")
    hold = bytearray(max(0, OBSERVER - initial["parts"]["anon"]))
    for index in range(0, len(hold), 4096):
        hold[index] = 1
    emit("observer", dict(kernel(path), pid=os.getpid(), pin=cpu, held_bytes=len(hold)))
    cmd = [sys.executable, "-IB", str(Path(__file__).resolve()), "trace", str(root), *flags]
    job = subprocess.run(cmd, cwd=root, check=False)
    emit("observer-end", dict(kernel(path), returncode=job.returncode, held_bytes=len(hold)))
    return job.returncode


if __name__ == "__main__":
    chosen, directory = sys.argv[1:3]
    if chosen == "trace":
        trace(Path(directory), sys.argv[3:])
    else:
        raise SystemExit(observe(Path(directory), int(sys.argv[3]), sys.argv[4:]))
