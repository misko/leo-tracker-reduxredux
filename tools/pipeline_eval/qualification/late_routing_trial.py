"""Run the frozen curvature gate on stored-native single-tile requests."""

import argparse
import os
import resource
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output
from ..scoring import validate_result
from ..variants import late_routing, v5_armijo_aligned_finish, v5_lean
from . import late_routing_sources as measured
from . import late_routing_worker as candidate
from .broad_search_budget import _case, frozen_inputs
from .full_receiver_comparison import SCREEN, full_roster, sha
from .pruned_finish_eval import execution_binding, source_tokens
from .short_receiver_figures import _frozen_roof

REPORT = SCREEN / "streamlined/late-routing"
METHOD = candidate.METHOD
STOCK = "v5_armijo_aligned_finish"
SALT = "held-doppler-curvature-v1"
SCHEDULE = {
    "DS26-0066": (0, (METHOD,)),
    "DS26-0287": (1, (METHOD,)),
    "DS26-0098": (2, (METHOD, STOCK)),
    "DS26-0146": (3, (STOCK, METHOD)),
}
TIMEOUT_S = 330


def lock():
    refs, inventory = _frozen_roof()
    roster = sorted(full_roster(refs, inventory))
    held = sorted(
        set(roster) - {"DS26-0066", "DS26-0287"},
        key=lambda ident: sha256(f"{SALT}/{ident}".encode()).digest(),
    )[:2]
    if held != ["DS26-0098", "DS26-0146"]:
        raise ValueError("original roof confirmation draw changed")
    frozen = frozen_inputs()
    inputs = {
        ident: execution_binding(frozen[ident], _case(frozen[ident])) for ident in SCHEDULE
    }
    return dict(
        sources={
            str(path): sha(path)
            for path in (
                Path(__file__),
                Path(late_routing.__file__),
                Path(candidate.__file__),
                REPORT / "PROTOCOL.md",
            )
        },
        aligned_sources=source_tokens(),
        cases=roster,
        held=held,
        jobs={ident: [pin, list(order)] for ident, (pin, order) in SCHEDULE.items()},
        inputs=inputs,
        timeout_s=TIMEOUT_S,
    )


def replay(ident, scratch):
    pin, order = SCHEDULE[ident]
    if os.sched_getaffinity(0) != {pin}:
        raise ValueError(f"configure the sealed CPU {pin} before launching")
    authority = REPORT / "run-lock.json"
    sealed, _ = measured.verify_run(REPORT, lock())
    case = _case(frozen_inputs()[ident])
    v5_lean.TIMEOUT_S = TIMEOUT_S
    scratch = local_output(scratch)
    for method in order:
        runner = candidate if method == METHOD else v5_armijo_aligned_finish
        started = perf_counter()
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        result = runner.run(case, scratch / ident / method)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        validate_result(result)
        row = dict(
            **sealed["inputs"][ident],
            method=method,
            source_lock_sha256=sha(authority),
            result=result,
            worker_wall_s=perf_counter() - started,
            worker_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        )
        (scratch / f"{ident}-{method}.json").write_bytes(encoded(row))
        print(ident, method, result["status"], round(row["worker_wall_s"], 2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["lock", *SCHEDULE])
    p.add_argument("--scratch", type=Path)
    args = p.parse_args()
    if args.action == "lock":
        with (REPORT / "run-lock.json").open("xb") as stream:
            stream.write(encoded(lock()))
    else:
        replay(args.action, args.scratch)
