"""Observe ordinary compact cavity code reach in separate diagnostic processes."""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

TOOL = 2
KEY = "ordinary-DS29-0082"


def worker(output, method, args):
    import functools

    roots = tuple(
        (name, str(Path(path).resolve()) + "/")
        for name, path in (
            ("checkout", os.environ["TRACE_CHECKOUT"]),
            ("frozen", os.environ["TRACE_FROZEN"]),
            ("frozen-runner", os.environ["TRACE_RUNNER"]),
            ("staged", os.environ["TRACE_STAGE"]),
        )
    )

    @functools.cache
    def path_for(code):
        path = code.co_filename
        if path == "<native-bound-original-boundaries>":
            return f"generated/{path}"
        if Path(path) == Path(__file__) or "/.venv/" in path:
            return None
        for name, prefix in roots:
            if path.startswith(prefix):
                return name + "/" + path[len(prefix) :]
        return None

    monitoring = sys.monitoring
    events = monitoring.events
    visited, scores, structures = defaultdict(set), {}, {}

    def enable(code, _offset):
        if path_for(code):
            monitoring.set_local_events(TOOL, code, events.LINE)
            structures[code] = path_for(code)
        return monitoring.DISABLE

    def line(code, lineno):
        visited[structures[code]].add(lineno)
        return monitoring.DISABLE

    def scientific_score(code, _offset, result):
        path = path_for(code)
        if path and isinstance(result, dict):
            selected = result.get("policy_arms") if code.co_name == "cavity_policy" else None
            if code.co_name == "signed_context" and path.endswith("/signed_context.py"):
                selected = result["arms"]
            if selected and all("negative_twice_elbo" in a for a in selected.values()):
                scores[code.co_name] = {
                    a: float(v["negative_twice_elbo"]) for a, v in selected.items()
                }

    monitoring.use_tool_id(TOOL, "direct cavity diagnostic")
    monitoring.register_callback(TOOL, events.PY_START, enable)
    monitoring.register_callback(TOOL, events.LINE, line)
    monitoring.register_callback(TOOL, events.PY_RETURN, scientific_score)
    monitoring.set_events(TOOL, events.PY_START | events.PY_RETURN)
    try:
        if method == "direct":
            from tools.pipeline_eval.variants.v5_direct_cavity import main

            sys.argv = [sys.argv[0], *args]
            main()
        else:
            from tools.pipeline_eval.variants.v5_secant_fit import worker as stock

            stock(*args)
    finally:
        monitoring.set_events(TOOL, 0)
        for code in structures:
            monitoring.set_local_events(TOOL, code, 0)
        for event in (events.PY_RETURN, events.PY_START, events.LINE):
            monitoring.register_callback(TOOL, event, None)
        monitoring.free_tool_id(TOOL)
        output.write_text(
            json.dumps(
                dict(
                    files={name: sorted(lines) for name, lines in sorted(visited.items())},
                    scores=scores,
                    forbidden_imports=sorted(
                        m
                        for m in sys.modules
                        if m.startswith(
                            (
                                "tools.pipeline_eval.qualification",
                                "tools.pipeline_eval.__main__",
                                "evaluate_accuracy_repair",
                                "evaluate_algo07",
                            )
                        )
                    ),
                ),
                allow_nan=False,
                sort_keys=True,
            )
        )


def collect(work, method):
    import subprocess
    from time import perf_counter
    from unittest.mock import patch

    from tools.pipeline_eval.qualification import direct_cavity_trial as trial

    if os.sched_getaffinity(0) != {5} or os.nice(0) < trial.NICE:
        raise ValueError("ordinary trace must run on CPU 5 at nice 10")
    plan = trial.common.read(work / "plan.json")
    case, request, tags = trial.input_case(KEY)
    if plan["sources"] != trial.sources() or tags != plan["bindings"][KEY]:
        raise ValueError("trace inputs or source differ from pilot lock")
    env = dict(
        TRACE_CHECKOUT=str(trial.common.ROOT),
        TRACE_FROZEN=str(trial.v5_lean.SOURCE),
        TRACE_RUNNER=str(trial.v5_lean.RUNNER),
        TRACE_STAGE=str(work / trial.RELEASE),
    )
    directory = work / "trace" / method
    directory.mkdir(parents=True, exist_ok=False)
    library = directory / "projection.so"
    trial.orbit_projector.compile_kernel(library)
    began, began_cpu = perf_counter(), trial.cpu_s()
    if method == "direct":
        stage = work / trial.RELEASE
        args = trial.direct_command(case, request["job"], stage, library)[4:]
        with (directory / "result.json").open("xb") as out, (directory / "log").open("xb") as log:
            try:
                subprocess.run(
                    [
                        str(trial.v5_lean.PYTHON),
                        "-B",
                        str(Path(__file__).resolve()),
                        "worker",
                        str(directory / "reach.json"),
                        "direct",
                        *args,
                    ],
                    env=dict(trial.command_env(stage), **env),
                    cwd=stage,
                    stdout=out,
                    stderr=log,
                    check=True,
                    timeout=165,
                )
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
                trial.save_json(directory / "failed.json", dict(error=str(exc)))
                return
        result = trial.common.read(directory / "result.json")
    else:
        with patch.dict(os.environ, env), patch.object(trial.v5_lean, "TIMEOUT_S", 165):
            result = trial.v5_lean.run_bound_worker(
                case, directory, Path(__file__), worker_args=(str(library), "secant")
            )
    trial.save_json(
        directory / "measurement.json",
        dict(
            tags,
            method=method,
            result=result,
            resources=trial.stamp(began, began_cpu),
            tracer_sha256=trial.common.sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    if sys.argv[1] == "worker":
        worker(Path(sys.argv[2]), sys.argv[3], sys.argv[4:])
    elif sys.argv[1] == "collect":
        collect(Path(sys.argv[2]).resolve(), sys.argv[3])
    else:
        request, result, *_ = sys.argv[1:]
        worker(Path(result).with_name("reach.json"), "stock", sys.argv[1:])
