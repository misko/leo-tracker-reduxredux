"""Observe standalone import footprint and science decisions in matched services."""

import json
import os
import resource
import runpy
import sys
from pathlib import Path
from time import monotonic, process_time

helpers = runpy.run_path(str(Path(__file__).with_name("ranked_fit_probe.py")))
emit, group, outcomes, resources = (
    helpers[name] for name in ("emit", "group", "outcomes", "resources")
)

WATCH = {
    ("v5_core.py", "ranked_initial_nodes"): "ranked",
    ("v5_core.py", "initial_selection"): "initial",
    ("conservative_recovery.py", "conservative_recovery"): "conservative",
    ("family_cavity.py", "nominate_families"): "nomination",
    ("family_cavity.py", "cavity_policy"): "cavity",
}


def node_identity(node):
    return sorted(
        (row["component"], int(row["candidate_index"]), int(row["candidate_norad"]), int(alias))
        for row, alias in zip(node["seed"]["rows"], node["aliases"], strict=True)
    )


def decision(name, result):
    if name == "ranked":
        return [node_identity(node) for node in result]
    if name == "initial":
        choices, branches = result
        return dict(
            branches=branches,
            winner=node_identity(choices["choices"][0]["node"]),
        )
    if name == "conservative":
        return dict(
            status=result["status"],
            node=node_identity(result["final_node"]) if "final_node" in result else None,
            mask=result["final_mask"].tolist() if "final_mask" in result else None,
        )
    if name == "nomination":
        return outcomes(result)
    return dict(
        status=result["status"],
        accepted=result.get("accepted"),
        replacements=[row.get("replacements") for row in result.get("trials", ())],
        valid=[row["paired_valid"] for row in result.get("trials", ())],
        selected=(result.get("selected") or {}).get("replacements"),
    )


def imports(root):
    local, external, standard = set(), set(), set()
    for name, module in tuple(sys.modules.items()):
        path = getattr(module, "__file__", None)
        top = name.partition(".")[0]
        if top in sys.stdlib_module_names:
            standard.add(top)
        elif path and Path(path).is_absolute() and Path(path).is_relative_to(root):
            local.add(str(Path(path).relative_to(root)))
        elif path and top not in {"__main__", "ranked_fit_probe"}:
            external.add(top)
    return dict(
        project=sorted(local), standard_library=sorted(standard), third_party=sorted(external)
    )


def run(root, cpu, arguments):
    # Match both binaries with the same tiny observer and exclude it from package counts.
    cgroup = group()
    before = resources(cgroup)
    if before["memory.max"] != 512 * 2**20 or before["memory.swap.max"]:
        raise ValueError("strict 512 MiB, zero-swap service required")
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10:
        raise ValueError("service placement departed from its declared pin")
    emit("ready", before | dict(cpu=cpu, nice=os.nice(0)))
    monitoring = sys.monitoring
    events = monitoring.events
    code_names, decisions = {}, {}

    def enter(code, _offset):
        path = Path(code.co_filename)
        name = WATCH.get((path.name, code.co_name))
        if name is None or not path.is_relative_to(root):
            return monitoring.DISABLE
        code_names[code] = name
        monitoring.set_local_events(4, code, events.PY_RETURN)
        return monitoring.DISABLE

    def leave(code, _offset, result):
        name = code_names[code]
        decisions[name] = decision(name, result)

    monitoring.use_tool_id(4, "compact receiver decisions")
    monitoring.register_callback(4, events.PY_START, enter)
    monitoring.register_callback(4, events.PY_RETURN, leave)
    monitoring.set_events(4, events.PY_START)
    sys.argv = [str(root), *arguments]
    start, cpu_start = monotonic(), process_time()
    try:
        runpy.run_path(str(root), run_name="__main__")
    finally:
        measured = dict(wall_s=monotonic() - start, cpu_s=process_time() - cpu_start)
        monitoring.set_events(4, 0)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        emit("finish", measured | resources(cgroup) | dict(rss_peak_kib=usage.ru_maxrss))
        emit("decisions", json.loads(json.dumps(decisions)))
        emit("imports", imports(root))


if __name__ == "__main__":
    run(Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3:])
