"""Measure actual constrained fit calls in an isolated standalone receiver process."""

import json
import runpy
import sys
from pathlib import Path
from time import monotonic, process_time

WATCH = {
    ("feasible.py", "constrained"): "constrained",
    ("feasible.py", "feasible_fit"): "phase_fits",
    ("feasible.py", "gate_slacks"): "gate_evaluations",
    ("polynomial_satellite_diagnostics.py", "batch_noise_screen"): "legacy_noise_screens",
    ("fit_work_projection.py", "__init__"): "prepared_curves",
    ("fit_work_projection.py", "__call__"): "prepared_noise_screens",
    ("native_bound.py", "__call__"): "native_bounds",
}


def run(root, flags):
    monitoring = sys.monitoring
    events = monitoring.events
    code_names, phases = {}, []
    active = None

    def start(code, _offset):
        nonlocal active
        name = code_names.get(code)
        if name is None:
            file = Path(code.co_filename)
            name = WATCH.get((file.name, code.co_name))
            if name is None or not file.is_relative_to(root):
                return monitoring.DISABLE
            code_names[code] = name
        if name == "constrained":
            if active is not None:
                raise ValueError("unexpected nested constrained refinement")
            monitoring.set_local_events(2, code, events.PY_RETURN)
            active = dict(
                began_cpu=process_time(),
                began_wall=monotonic(),
                calls=dict.fromkeys(WATCH.values(), 0),
            )
        if active is not None:
            active["calls"][name] += 1
        return None

    def returned(_code, _offset, _result):
        nonlocal active
        phase = dict(
            calls=active["calls"],
            cpu_s=process_time() - active["began_cpu"],
            wall_s=monotonic() - active["began_wall"],
        )
        phases.append(phase)
        active = None

    monitoring.use_tool_id(2, "bounded constrained fit counters")
    monitoring.register_callback(2, events.PY_START, start)
    monitoring.register_callback(2, events.PY_RETURN, returned)
    monitoring.set_events(2, events.PY_START)
    sys.argv = [str(root), *flags]
    try:
        runpy.run_path(str(root), run_name="__main__")
    finally:
        monitoring.set_events(2, 0)
        for code in code_names:
            monitoring.set_local_events(2, code, 0)
        for event in (events.PY_START, events.PY_RETURN):
            monitoring.register_callback(2, event, None)
        monitoring.free_tool_id(2)
        print("fit-work-count " + json.dumps(dict(phases=phases)), file=sys.stderr, flush=True)


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), sys.argv[2:])
