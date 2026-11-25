"""Compare three fine-salvage variants during one authentic saved DS30-0218 prefix."""

from argparse import ArgumentParser
from contextlib import contextmanager
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from shutil import copyfile
import subprocess
import sys
from time import perf_counter_ns, process_time_ns, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import masked_cfo_0218_capsule as capsule
import rescue_phase_prepare
import salvage_projection
from masked_cfo_0218 import saved, signed


DONOR = Path("/dev/shm/leo-v3-0218-prospective01")
PLAN = "06db08f484a07cd1c3cc49e07ec04e0384eb3506bed54400584bca355e1f78d8"
SOURCE_PINS = {
    "plan.json": PLAN,
    "admission.json": "3ef1a8380e411fd7b54b3a87ddd49572a6c80baee72388da0244d067160cc090",
    "derived-native.json": "bd3d58c67c87f198814cecfc3c0a3fed402103a909b5438f300cab4160e798dc",
    "substituted/exact-named-raw-witness.json": "d4c0d1b6dfa1ba90c380c3d29df4965b6330bebc729bee3f5a478258f6bbefd8",
}
CAP_S = 17


class AfterSalvage(BaseException):
    """End after the original ordered recovery choices and before further fits."""


def sources():
    return {Path(module.__file__).name: saved.identifier(Path(module.__file__))
            for module in (salvage_projection, rescue_phase_prepare, capsule)} | {
        Path(__file__).name: saved.identifier(Path(__file__)),
    }


def command(cell, mounts, *, smoke):
    parent = capsule.command(cell, PLAN, "ordinary", mounts, proof_only=smoke)
    # Keep the previously checked mount isolation and substitute just its worker entry.
    return parent[:parent.index("--") + 3] + [str(Path(__file__)), "child", str(cell),
                                             *(["--smoke"] if smoke else [])]


def enrollment(cell, *, smoke, observation_scope=None):
    plan = saved.document(cell/"plan.json", PLAN)
    return saved.worker(cell, PLAN, capsule.held.experiment(probe=False), smoke=smoke, lease_fd=0,
                        enrollment=(plan["case"], Path(plan["stage"]), plan["admission_sha256"], plan["references"]),
                        admission_path=cell/"admission.json", original_control=True, observation_scope=observation_scope)


def require_new_cell(cell):
    if cell.parent != DONOR or not cell.name.startswith("fine-projection-") or cell.resolve() != cell:
        raise ValueError("Use a fresh direct fine-projection cell beside the already enrolled stage")


def prepare(cell):
    require_new_cell(cell)
    cell.mkdir(mode=0o700)
    original = DONOR/"ordinary"
    for name in capsule.ram.ARTIFACTS:
        saved.document(original/name, SOURCE_PINS[name])
        copyfile(original/name, cell/name)
        (cell/name).chmod(0o400)
    stage = saved.document(original/"substituted/exact-named-raw-witness.json",
                           SOURCE_PINS["substituted/exact-named-raw-witness.json"])
    history = stage["ports"]["history_risk"]
    lean, = history["lean_attempts"]
    saved.write(cell/"reference.json", dict(original_witness=SOURCE_PINS["substituted/exact-named-raw-witness.json"],
        salvage=lean["support"]["salvage"], coarse_shortlists=lean["salvage_shortlists"],
        counts=lean["certified_salvage"], cold=lean["cold"], clocks=stage["timing"], sources=sources()))
    _, inputs, mounts = capsule.operands(cell, PLAN, "ordinary")
    capsule.setup(cell)
    with (cell/"plan.json").open("rb") as descriptor:
        proof = subprocess.run(command(cell, mounts, smoke=True), capture_output=True, text=True,
                               stdin=descriptor, check=True, timeout=12)
    observed = json.loads(proof.stdout)
    if observed != dict(case="DS30-0218", changed=0, refs=50, acquired=0, waveform_reads=0, solver_runs=0):
        raise ValueError("The unchanged original handoff did not pass the isolated smoke")
    saved.write(cell/"ready.json", dict(inputs=list(map(str, inputs)), sources=sources(), smoke=observed,
               isolation=saved.identifier(cell/"preflight-isolation.json"), reference=saved.identifier(cell/"reference.json")))


def child(cell, *, smoke):
    start_wall, start_cpu = perf_counter_ns(), process_time_ns()
    stage = Path(saved.document(cell/"plan.json", PLAN)["stage"])
    proof = capsule.isolation(cell, stage, probe=smoke)
    saved.write(cell/("preflight-isolation.json" if smoke else "worker-isolation.json"), proof)
    sys.addaudithook(saved.deny_backing)
    if smoke:
        enrollment(cell, smoke=True)
        import certified_salvage

        salvage_projection.checked_ports(certified_salvage.fine_alternatives)
        return
    saved.attrs(expected_priority="idle")
    audit, salvage = [], {}

    @contextmanager
    def observe(native):
        import blind_joint_finish
        from leo.analysis.localization_v3 import orbits
        from live_orbit_setup_audit import Trace, compare_bulk

        trace = Trace()
        baseline = saved.document(cell/"reference.json")
        if signed.canonical(native) != "sha256:" + SOURCE_PINS["derived-native.json"]:
            raise ValueError("The numerical prefix received another original packet")

        def stop(references, proposals):
            if proposals != baseline["salvage"]:
                raise ValueError("The observed original recovery choices differ from the sealed field replay")
            original = [row["counters"]["ordinary"] for row in audit]
            if (len(audit) != len(proposals) or len(audit) != len(baseline["coarse_shortlists"])
                    or any(sum(row.get(key, 0) for row in original) != baseline["counts"][key]
                           for key in ("support_trials", "interval_rejected", "dominated", "profile_calls", "noise_calls"))):
                raise ValueError("The replay did not reach the complete original certified fine scope")
            salvage.update(alternatives_sha256=signed.canonical(proposals), orbit_calls=compare_bulk(trace.calls),
                           orbit_observer_cpu_ns=trace.trace_cpu_ns)
            raise AfterSalvage

        with (salvage_projection.binding(audit=audit),
              patch.object(orbits, "propagate_grid", trace.propagator(orbits.propagate_grid)),
              patch.object(blind_joint_finish, "rescued_references", stop)):
            yield

    try:
        enrollment(cell, smoke=False, observation_scope=observe)
    except AfterSalvage:
        usage = getrusage(RUSAGE_SELF)
        saved.write(cell/"slice.json", dict(salvage, audit=audit, plan=PLAN, sources=sources(),
                    child_elapsed_ns=perf_counter_ns()-start_wall, child_cpu_ns=process_time_ns()-start_cpu,
                    child_input_blocks=usage.ru_inblock, major_faults=usage.ru_majflt, waveform_reads=0,
                    boundary="saved handoff through original ordered salvage choices, before second curved gate"))
    else:
        raise ValueError("The bounded worker unexpectedly progressed past salvage")


def launch(cell, driver, watching_from):
    require_new_cell(cell)
    if (os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"
            or any(os.environ.get(key) != "1" for key in capsule.ram.THREADS)):
        raise ValueError("Use the low-priority CPU3 controller with one numerical thread")
    ready = saved.document(cell/"ready.json")
    _, inputs, mounts = capsule.operands(cell, PLAN, "ordinary")
    if (ready["sources"] != sources() or ready["inputs"] != list(map(str, inputs))
            or ready["reference"] != saved.identifier(cell/"reference.json")
            or ready["isolation"] != saved.identifier(cell/"preflight-isolation.json")
            or (cell/"worker-intent.json").exists()):
        raise ValueError("Require the exact unused preflighted prefix")
    event = capsule.recent_deferral(capsule.held.CAMPAIGN, watching_from, time_ns())
    if event is None:
        raise ValueError("No eligible fresh official storage deferral")
    capsule.live_window(event, driver)
    quiet = capsule.ram.nvme_quiet(continuous=True)
    with capsule.lease() as descriptor:
        saved.require_resident(inputs)
        capsule.live_window(event, driver)
        quiet_lease = capsule.ram.nvme_quiet(continuous=False)
        saved.write(cell/"worker-intent.json", dict(event=event, cap_s=CAP_S, quiet=quiet, quiet_lease=quiet_lease))
        arguments = ["/usr/bin/time", "-f", "%e %U %S %I %F", "-o", str(cell/"time.txt"), "/usr/bin/timeout",
                     "--kill-after=1s", f"{CAP_S}s", "/usr/bin/taskset", "-c", "2", *command(cell, mounts, smoke=False)]
        wall = perf_counter_ns()
        with (cell/"worker.stdout").open("xb") as stdout, (cell/"worker.stderr").open("xb") as stderr:
            result = subprocess.run(arguments, stdin=descriptor, stdout=stdout, stderr=stderr, check=False)
        elapsed = perf_counter_ns()-wall
    saved.write(cell/"exit.json", dict(exit_code=result.returncode, elapsed_ns=elapsed,
                slice=saved.identifier(cell/"slice.json") if result.returncode == 0 else None))
    return result.returncode


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "child", "launch"))
    parser.add_argument("cell", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--driver", type=int)
    parser.add_argument("--watching-from", type=int)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.cell)
    elif args.mode == "child":
        child(args.cell, smoke=args.smoke)
    else:
        if args.driver is None or args.watching_from is None:
            parser.error("launch requires --driver and --watching-from")
        sys.exit(launch(args.cell, args.driver, args.watching_from))
