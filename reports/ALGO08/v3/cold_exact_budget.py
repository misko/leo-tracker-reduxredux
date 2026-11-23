"""Profile the actual initial discovery inside an authenticated saved publication."""

import argparse
from contextlib import ExitStack, contextmanager
import cProfile
from functools import partial
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
    from leo.analysis.localization_v3.discovery import signature
    from tools.pipeline_eval.variants import v5_core

    audit = []
    original = cold_finalist_race.refine

    def refine(*args, **options):
        ranks, stages, ordered = [], [], []
        profile = cProfile.Profile(timer=process_time_ns, timeunit=1e-9) if profiled else None
        rank = timed(v5_core.ranked_initial_nodes, ranks)

        def record(current):
            nodes = rank(current)
            ordered.extend(signature(node) for node in nodes)
            return nodes

        with patch.object(v5_core, "ranked_initial_nodes", record):
            operation = timed(original, stages)
            result = profile.runcall(operation, *args, **options) if profiled else operation(*args, **options)
        rows = []
        if profile is not None:
            for (file, line, function), (primitive, calls, own, cumulative, _) in pstats.Stats(profile).stats.items():
                rows.append(dict(file=file, line=line, function=function, primitive=primitive, calls=calls,
                                 cpu_s=own, inclusive_cpu_s=cumulative))
            rows.sort(key=lambda item: (-item["cpu_s"], item["file"], item["line"]))
        audit.append(dict(scopes=stages, ranks=ranks, profile_rows=rows,
                          selected=result[3], endpoint=result[1], phase_reference=result[2], ordered=ordered))
        return result

    with patch.object(cold_finalist_race, "refine", refine):
        yield audit


def worker(request, inventory, output, mode, case):
    import empty_bootstrap as installed
    from aperture_trial import write
    from provisional_salvage_trial import PINS
    from prospective_0316_solver import worker as ordinary

    saved_runtime = installed.load_runtime
    audits = []
    profiled = mode == "profile"
    with ExitStack() as stack:
        def runtime():
            loaded = saved_runtime()
            if mode == "borrow":
                import cold_track_row_entry as entry

                stack.enter_context(patch.object(entry, "shared_association_rows",
                                                 partial(entry.shared_association_rows, borrow=True)))
            audits.append(stack.enter_context(controlled_cold(profiled)))
            return loaded

        stack.enter_context(patch.object(installed, "load_runtime", runtime))
        ordinary(request, "cumulative", output, inventory_file=inventory, source_pins=PINS | {
            "unified_short_bootstrap.py": "89567f7c5ceaae7cff38268747c85aa8bc9d843638560dea0a6b78c88102560d",
        }, **dict(settings(case), audit_name=AUDIT))
    if len(audits) != 1 or len(audits[0]) != 1 or len(audits[0][0]["ranks"]) != 1:
        raise ValueError("The named saved publication did not price one original cold rank")
    write(output / "cold-scopes.json", dict(profiled=profiled, work=audits[0][0]))


def settings(case):
    from provisional_salvage_dense import SETTINGS
    from provisional_salvage_trial import settings as medium

    return SETTINGS if case == "dense" else medium("DS30-0316")


def assigned(case):
    from provisional_salvage_dense import preflight
    from provisional_salvage_trial import saved_request

    if case == "medium":
        return saved_request("DS30-0316")
    request, inventory, _ = preflight()
    return request, inventory


def run(root, mode, case):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from joint_publication import artifacts
    from provisional_salvage_dense import CONTROL, TRACE_SHA
    from prospective_0316_solver import inspect
    from prospective_small_physical import checked
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-T", str(root.parent), "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs outputs for dense profiling")
    request, inventory = assigned(case)
    root.mkdir()
    (root / "tmp").mkdir()
    if case == "dense":
        expected = json.loads(checked(CONTROL / "reused/joint-research-receipt.json", TRACE_SHA))
    else:
        prior = Path("/dev/shm/leo-v3-saved-0316-pair-01/cumulative/joint-research-receipt.json")
        expected = json.loads(checked(prior, "cc34b01ee1145cbc7f9388eab33da5e120011a86c0911f8876260ca9ad27ab25"))
    pin_files = (Path(__file__), HERE / "cold-exact-budget-protocol.md", HERE / "cold_finalist_race.py",
                 HERE / "joint_publication.py", HERE / "unified_short_bootstrap.py", HERE / "cold_track_row_reuse.py",
                 HERE / "cold-borrowed-rows-protocol.md")
    write(root / "binding.json", dict(machine=machine, request=request, inventory=str(inventory), mode=mode, case=case,
                                      source={path.name: sha256(path.read_bytes()).hexdigest() for path in pin_files}))
    job = root / "request.json"
    write(job, request)
    out = root / mode
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-IB", Path(__file__), "worker", out, "--request", job,
               "--inventory", inventory, "--mode", mode, "--case", case]
    clock = measure(command, env, out)
    write(root / "clock.json", clock)
    if clock["exit_code"]:
        raise ValueError(f"The saved worker failed. See {out.with_suffix('.stderr')}")
    result = read(out / AUDIT)
    compared = inspect(out, "cumulative", result["receipt"], clock, request, **dict(settings(case), audit_name=AUDIT))
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
    parser.add_argument("--mode", choices=("profile", "control", "borrow"), default="profile")
    parser.add_argument("--case", choices=("dense", "medium"), default="dense")
    args = parser.parse_args()
    if args.stage == "run":
        run(args.output, args.mode, args.case)
    else:
        worker(args.request, args.inventory, args.output, args.mode, args.case)
