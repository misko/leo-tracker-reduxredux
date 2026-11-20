"""Count executed local Python lines in separate, source-bound replay workers."""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter, time_ns
from unittest.mock import patch

from tools.pipeline_eval.__main__ import ROOT, local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_lean

RECEIVER = "v5_compact_receiver"
CONTROL = "v5_recovery_reads"
TOOL = 2


def local_path(name):
    for prefix, tag in (
        (str(ROOT) + "/", ""),
        (str(v5_lean.SOURCE) + "/", "frozen-v5/"),
        (str(v5_lean.RUNNER) + "/", "frozen-runner/"),
    ):
        if name.startswith(prefix):
            return tag + name[len(prefix) :]
    return None


def traced_path(code):
    name = local_path(code.co_filename)
    if name is None or name.endswith("/compact_entry_trace.py"):
        return None
    if (
        code.co_firstlineno == 1
        and code.co_name in ("screen_candidates", "screen")
        and name.endswith(("/residual_screen.py", "/reassociation_screen.py"))
    ):
        return f"{name}#{code.co_name}-rewritten"
    return name


def worker(request, output, library, method):
    reach, functions, paths = defaultdict(set), defaultdict(set), {}
    monitoring = sys.monitoring
    events = monitoring.events

    def start(code, offset):
        name = traced_path(code)
        if name is not None:
            paths[code] = name
            functions[name].add((code.co_qualname, code.co_firstlineno))
            monitoring.set_local_events(TOOL, code, events.LINE)
        return monitoring.DISABLE

    def line(code, number):
        reach[paths[code]].add(number)
        return monitoring.DISABLE

    monitoring.use_tool_id(TOOL, "compact entry line audit")
    monitoring.register_callback(TOOL, events.PY_START, start)
    monitoring.register_callback(TOOL, events.LINE, line)
    monitoring.set_events(TOOL, events.PY_START)
    try:
        if method == RECEIVER:
            from tools.pipeline_eval.variants.v5_compact_receiver import worker as numerical
        else:
            from tools.pipeline_eval.qualification.recovery_reads_worker import worker as numerical
        numerical(request, output, library)
    finally:
        monitoring.set_events(TOOL, 0)
        for code in tuple(paths):
            monitoring.set_local_events(TOOL, code, 0)
        monitoring.register_callback(TOOL, events.PY_START, None)
        monitoring.register_callback(TOOL, events.LINE, None)
        monitoring.free_tool_id(TOOL)
        save_json(
            Path(output).with_name("lines.json"),
            dict(
                files={
                    name: dict(lines=sorted(lines), functions=sorted(functions[name]))
                    for name, lines in sorted(reach.items())
                },
                qualification_imports=sorted(
                    k for k in sys.modules if k.startswith("tools.pipeline_eval.qualification.")
                ),
            ),
        )


def run(method, plan_path, parent):
    from tools.pipeline_eval.qualification import compact_entry_trial as trial
    from tools.pipeline_eval.qualification.secant_end_to_end_worker import cpu_s, stamp

    lock = trial.common.read(plan_path)
    if (
        os.sched_getaffinity(0) != {12}
        or os.nice(0) < trial.NICE
        or lock["source"] != trial.source()
    ):
        raise ValueError("trace requires the original ordinary pin and source")
    key = "ordinary-DS29-0082"
    request, binding = trial.case(key)
    if binding != lock["bindings"][key]:
        raise ValueError("trace request differs from normal measurement")
    budget = min(145, (lock["locked_ns"] + trial.TOTAL * 10**9 - time_ns()) // 10**9)
    if budget <= 5:
        raise ValueError("no unspent qualification time for the separate trace")
    folder = local_output(parent) / method
    folder.mkdir(parents=True, exist_ok=False)
    kernel = folder / "orbit_projector.so"
    start, cpu = perf_counter(), cpu_s()
    orbit_projector.compile_kernel(kernel)
    with patch.object(v5_lean, "TIMEOUT_S", budget - 5):
        result = v5_lean.run_bound_worker(
            request, folder, Path(__file__), worker_args=(str(kernel), method)
        )
    measured = stamp(start, cpu)
    if "exceeded its " in result.get("reason", ""):
        result["status"] = "timed_out"
    save_json(
        folder / "measurement.json",
        dict(
            binding,
            method=method,
            cpu=12,
            resources=measured,
            result=result,
            trace_source_sha256=trial.common.sha(Path(__file__)),
        ),
    )
    print(method, result["status"], measured["wall_s"], flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] not in (CONTROL, RECEIVER):
        worker(*sys.argv[1:])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("method", choices=(RECEIVER, CONTROL))
        parser.add_argument("plan", type=Path)
        parser.add_argument("--out", required=True, type=Path)
        args = parser.parse_args()
        run(args.method, args.plan, args.out)
