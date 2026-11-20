"""Count live ranked nomination and time orbital-mode preparation."""

import json
import os
import resource
import runpy
import sys
from hashlib import sha256
from pathlib import Path
from time import monotonic, process_time

WATCH = {
    ("direct_lifetime_kernels.py", "nominate"): "nominate",
    ("family_cavity.py", "family_data"): "family_data",
    ("direct_lifetime_kernels.py", "screen"): "screen",
    ("family_cavity.py", "candidate_prediction"): "candidate",
    ("orbit_modes.py", "build_modes"): "build_modes",
}


def group():
    line = next(
        x for x in Path("/proc/self/cgroup").read_text().splitlines() if x.startswith("0::")
    )
    return Path("/sys/fs/cgroup") / line[3:].lstrip("/")


def resources(path):
    return {
        name: int((path / name).read_text())
        for name in ("memory.max", "memory.peak", "memory.swap.max", "memory.swap.current")
    }


def emit(name, data):
    print(name + " " + json.dumps(data, separators=(",", ":")), file=sys.stderr, flush=True)


def outcomes(result):
    def item(offer):
        if offer is None:
            return None
        return (
            offer["candidate_index"],
            offer["norad"],
            float(offer["score"]).hex(),
            float(offer["phase_s"]).hex(),
            float(offer["phase_change_s"]).hex(),
            float(offer["minimum_elevation_deg"]).hex(),
            float(offer["conditional_RMS_hz"]).hex(),
            list(map(int, offer["aliases"])),
            offer["qualified"],
            offer["physical_modes"],
        )

    ranked = [
        (
            family["original_index"],
            family["held_points"],
            family["held_observation_ids"],
            family["coarse_candidate_count"],
            [item(record) for record in family["candidates"]],
            item(family["best"]),
        )
        for family in result.get("families", [])
    ]
    encoded = json.dumps(ranked, separators=(",", ":")).encode()
    return dict(
        families=len(ranked),
        candidate_counts=[len(family[4]) for family in ranked],
        ordered_fine_outcomes_sha256=sha256(encoded).hexdigest(),
        status=result["status"],
    )


def run(root, cpu, flags):
    path = group()
    start = resources(path)
    if start["memory.max"] != 512 * 2**20 or any(
        start[name] for name in ("memory.swap.max", "memory.swap.current")
    ):
        raise ValueError("ranked nomination requires the declared physical cap")
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10:
        raise ValueError("ranked nomination affinity or nice level changed")
    emit("ready", start | {"cpu": cpu, "nice": os.nice(0)})
    monitor = sys.monitoring
    events = monitor.events
    names, active = {}, {}
    counts, cpu_s = {}, {}

    def entered(code, _offset):
        name = names.get(code)
        if name is None:
            source = Path(code.co_filename)
            name = WATCH.get((source.name, code.co_name))
            if name is None or not source.is_relative_to(root):
                return monitor.DISABLE
            names[code] = name
            monitor.set_local_events(2, code, events.PY_RETURN)
        if name != "nominate" and "nominate" not in active:
            return None
        slot = name
        if name == "build_modes":
            if "candidate" not in active:
                return None
            args = sys._getframe(1).f_locals
            slot = "mode_with_support" if args["supported"] else "mode_without_support"
        elif name == "candidate":
            args = sys._getframe(1).f_locals
            j, data = args["j"], args["data"]
            if j not in data["p"].supported and data["held_owners"] < 2:
                counts["candidates_without_modes"] = counts.get("candidates_without_modes", 0) + 1
        active[name] = slot, process_time()
        counts[slot] = counts.get(slot, 0) + 1
        return None

    def returned(code, _offset, result):
        name = names[code]
        pending = active.pop(name, None)
        if pending is None:
            return
        slot, began = pending
        cpu_s[slot] = cpu_s.get(slot, 0.0) + process_time() - began
        if name == "nominate":
            emit("nomination", outcomes(result) | {"calls": counts, "cpu_s": cpu_s})

    monitor.use_tool_id(2, "ranked cavity nomination")
    monitor.register_callback(2, events.PY_START, entered)
    monitor.register_callback(2, events.PY_RETURN, returned)
    monitor.set_events(2, events.PY_START)
    sys.argv = [str(root), *flags]
    beginning = monotonic()
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
            resources(path)
            | {
                "cpu_s": process_time(),
                "elapsed_s": monotonic() - beginning,
                "rss_peak_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
        )


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), int(sys.argv[2]), sys.argv[3:])
