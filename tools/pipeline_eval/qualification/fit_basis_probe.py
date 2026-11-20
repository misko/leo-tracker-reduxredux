"""Measure the fixed working scope or check full candidate statistics in shadow."""

import ast
import json
import os
import resource
import runpy
import sys
from pathlib import Path
from time import monotonic, process_time

TARGET = "leo/analysis/localization_v3/discovery.py"
WATCH = {
    ("discovery.py", "statistics"),
    ("shared_orbit_phase_fit.py", "augment_phase_statistics"),
}


def emit(tag, data):
    print(tag + " " + json.dumps(data, separators=(",", ":")), file=sys.stderr, flush=True)


def cgroup():
    lines = Path("/proc/self/cgroup").read_text().splitlines()
    line = next(line for line in lines if line.startswith("0::"))
    return Path("/sys/fs/cgroup") / line[3:].lstrip("/")


def memory(group):
    return {
        key: int((group / key).read_text())
        for key in ("memory.max", "memory.swap.max", "memory.swap.current", "memory.peak")
    }


def measured(root):
    monitoring = sys.monitoring
    events = monitoring.events
    active, calls, durations = {}, {}, {}

    def start(code, _offset):
        if code not in active:
            file = Path(code.co_filename)
            if not file.is_relative_to(root) or (file.name, code.co_name) not in WATCH:
                return monitoring.DISABLE
            monitoring.set_local_events(2, code, events.PY_RETURN)
        active[code] = process_time()
        calls[code.co_name] = calls.get(code.co_name, 0) + 1
        return None

    def end(code, _offset, _result):
        key = code.co_name
        durations[key] = durations.get(key, 0.0) + process_time() - active[code]

    monitoring.use_tool_id(2, "discovery statistic timing")
    monitoring.register_callback(2, events.PY_START, start)
    monitoring.register_callback(2, events.PY_RETURN, end)
    monitoring.set_events(2, events.PY_START)
    try:
        runpy.run_path(str(root), run_name="__main__")
    finally:
        monitoring.set_events(2, 0)
        for code in active:
            monitoring.set_local_events(2, code, 0)
        for event in (events.PY_START, events.PY_RETURN):
            monitoring.register_callback(2, event, None)
        monitoring.free_tool_id(2)
        emit("statistics", dict(calls=calls, process_cpu_s=durations))


class WitnessComplete(Exception):
    pass


def shadow(root, revised):
    runpy.run_path(str(root))["activate"](root)
    import numpy as np
    from leo.analysis.localization_v3 import discovery

    parsed = ast.parse((revised / TARGET).read_bytes())
    definition = next(
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name == "statistics"
    )
    scope = dict(vars(discovery))
    exec(compile(ast.Module([definition], []), str(revised / TARGET), "exec"), scope)
    proposed = scope["statistics"]
    statistics, augment = discovery.statistics, discovery.augment_phase_statistics
    recent = None
    receipts = []

    def remember(*args, **kwargs):
        nonlocal recent
        result = statistics(*args, **kwargs)
        recent = args, kwargs, result
        return result

    def show(stats, times, frequency, derivative):
        args, kwargs, prior = recent
        if prior is not stats or args[1]["doppler_0"] is not frequency:
            raise ValueError("stock no longer combines the exact same observation basis")
        expected = augment(stats, times, frequency, derivative)
        actual = proposed(*args, **kwargs, phase_derivative=derivative)
        if actual.keys() != expected.keys():
            raise ValueError("fused moment fields differ")
        fragments = expected["fragments"]
        if not all(a is b for a, b in zip(fragments, actual["fragments"], strict=True)):
            raise ValueError("fused observation rows differ")
        for key, v in expected.items():
            if isinstance(v, np.ndarray):
                other = actual[key]
                if (
                    other.dtype != v.dtype
                    or other.shape != v.shape
                    or other.tobytes(order="C") != v.tobytes(order="C")
                ):
                    raise ValueError(f"fused {key} failed exact wide-factor parity")
        rows, satellites = expected["mean"].shape
        receipts.append(
            dict(
                rows=rows,
                satellites=satellites,
                orbit_observation_pairs=satellites * sum(map(int, expected["n"])),
                exact_fields=len(expected) - 1,
            )
        )
        if len(receipts) == 3:
            raise WitnessComplete
        return expected

    discovery.statistics, discovery.augment_phase_statistics = remember, show
    try:
        runpy.run_path(str(root), run_name="__main__")
    except WitnessComplete:
        emit("witness", receipts)
    else:
        raise ValueError("fewer than three authentic candidate inventories")


def main():
    root, cpu, mode = Path(sys.argv[1]).resolve(), int(sys.argv[2]), sys.argv[3]
    group = cgroup()
    initial = memory(group)
    if initial["memory.max"] != 512 * 2**20 or any(
        initial[key] for key in ("memory.swap.max", "memory.swap.current")
    ):
        raise ValueError("the fitted basis job requires the declared physical cgroup")
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10:
        raise ValueError("unexpected runtime CPU affinity or nice level")
    emit("ready", initial | {"cpu": cpu})
    revised, flags = Path(sys.argv[4]), sys.argv[5:]
    sys.argv = [str(root), *flags]
    begin = monotonic()
    try:
        if mode == "witness":
            shadow(root, revised)
        else:
            measured(root)
    finally:
        emit(
            "finish",
            memory(group)
            | dict(
                process_cpu_s=process_time(),
                wall_s=monotonic() - begin,
                rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            ),
        )


if __name__ == "__main__":
    main()
