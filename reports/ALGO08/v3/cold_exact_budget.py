"""Profile the actual initial discovery inside an authenticated saved publication."""

import argparse
from contextlib import ExitStack, contextmanager
import cProfile
from hashlib import sha256
import json
from pathlib import Path
import pstats
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
AUDIT = "cold-budget-worker.json"


def timed(operation, measurements):
    def measure(*args, **options):
        start = process_time_ns(), perf_counter_ns()
        try:
            return operation(*args, **options)
        finally:
            measurements.append(dict(cpu_ns=process_time_ns() - start[0],
                                     elapsed_ns=perf_counter_ns() - start[1]))
    return measure


@contextmanager
def controlled_cold(profiled):
    import cold_finalist_race
    from tools.pipeline_eval.variants import v5_core

    audit = []
    original = cold_finalist_race.refine

    def refine(*args, **options):
        ranks, stages = [], []
        profile = cProfile.Profile(timer=process_time_ns, timeunit=1e-9) if profiled else None
        with patch.object(v5_core, "ranked_initial_nodes", timed(v5_core.ranked_initial_nodes, ranks)):
            operation = timed(original, stages)
            result = profile.runcall(operation, *args, **options) if profiled else operation(*args, **options)
        rows = []
        if profile is not None:
            for (file, line, function), (primitive, calls, own, cumulative, _) in pstats.Stats(profile).stats.items():
                rows.append(dict(file=file, line=line, function=function, primitive=primitive, calls=calls,
                                 cpu_s=own, inclusive_cpu_s=cumulative))
            rows.sort(key=lambda item: (-item["cpu_s"], item["file"], item["line"]))
        audit.append(dict(scopes=stages, ranks=ranks, profile_rows=rows,
                          selected=result[3], endpoint=result[1], phase_reference=result[2]))
        return result

    with patch.object(cold_finalist_race, "refine", refine):
        yield audit


def worker(request, inventory, output, profiled):
    import empty_bootstrap as installed
    from aperture_trial import write
    from provisional_salvage_dense import SETTINGS
    from provisional_salvage_trial import PINS
    from prospective_0316_solver import worker as ordinary

    saved_runtime = installed.load_runtime
    audits = []
    with ExitStack() as stack:
        def runtime():
            loaded = saved_runtime()
            audits.append(stack.enter_context(controlled_cold(profiled)))
            return loaded

        stack.enter_context(patch.object(installed, "load_runtime", runtime))
        ordinary(request, "cumulative", output, inventory_file=inventory, source_pins=PINS | {
            "unified_short_bootstrap.py": "89567f7c5ceaae7cff38268747c85aa8bc9d843638560dea0a6b78c88102560d",
        }, **dict(SETTINGS, audit_name=AUDIT))
    if len(audits) != 1 or len(audits[0]) != 1 or len(audits[0][0]["ranks"]) != 1:
        raise ValueError("The named saved publication did not price one original cold rank")
    write(output / "cold-scopes.json", dict(profiled=profiled, work=audits[0][0]))


def assigned():
    from provisional_salvage_dense import preflight

    request, inventory, _ = preflight()
    return request, inventory


def run(root, mode):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from joint_publication import artifacts
    from provisional_salvage_dense import CONTROL, SETTINGS, TRACE_SHA
    from prospective_0316_solver import inspect
    from prospective_small_physical import checked
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-T", str(root.parent), "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs outputs for dense profiling")
    request, inventory = assigned()
    root.mkdir()
    (root / "tmp").mkdir()
    expected = json.loads(checked(CONTROL / "reused/joint-research-receipt.json", TRACE_SHA))
    pin_files = (Path(__file__), HERE / "cold-exact-budget-protocol.md", HERE / "cold_finalist_race.py",
                 HERE / "joint_publication.py", HERE / "unified_short_bootstrap.py")
    write(root / "binding.json", dict(machine=machine, request=request, inventory=str(inventory), mode=mode,
                                      source={path.name: sha256(path.read_bytes()).hexdigest() for path in pin_files}))
    job = root / "request.json"
    write(job, request)
    out = root / mode
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-IB", Path(__file__), "worker", out, "--request", job,
               "--inventory", inventory, "--mode", mode]
    clock = measure(command, env, out)
    write(root / "clock.json", clock)
    if clock["exit_code"]:
        raise ValueError(f"The saved worker failed. See {out.with_suffix('.stderr')}")
    result = read(out / AUDIT)
    compared = inspect(out, "cumulative", result["receipt"], clock, request, **dict(SETTINGS, audit_name=AUDIT))
    candidates = read(out / "joint-research-receipt.json")
    visual = artifacts(out, result["receipt"])
    from leo.contracts.digests import canonical_digest

    if (candidates["selected_rows"] != expected["selected_rows"]
            or expected["receipt"]["terminal_sha256"] != candidates["receipt"]["terminal_sha256"]
            or canonical_digest(visual["images"]) != canonical_digest(expected["evidence"]["images"])):
        raise ValueError("The full saved profiled worker did not preserve named dense science and PNGs")
    write(root / "result.json", dict(
        mode=mode, clock=clock, solve=result["solve"], layout=result["layout"], stages=read(out / "cold-scopes.json"),
        evidence=compared["science"], figures=visual["images"], selected_rows=canonical_digest(candidates["selected_rows"]),
        scientific_parity=True, binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest(),
    ))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("run", "worker"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--mode", choices=("profile", "control"), default="profile")
    args = parser.parse_args()
    if args.stage == "run":
        run(args.output, args.mode)
    else:
        worker(args.request, args.inventory, args.output, args.mode == "profile")
