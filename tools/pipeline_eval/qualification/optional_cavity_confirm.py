"""Repeat the two failed curved-incumbent calls under the same paired gate."""

import argparse
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter, process_time

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import v5_cavity_isolation
from . import optional_cavity_trial as trial
from .portable_gate_trials import checksum

LANES = {"DS26-0191": 5, "DS26-0199": 6}


def frozen():
    return dict(
        original=trial.source(),
        adapter=checksum(Path(v5_cavity_isolation.__file__)),
        runner=checksum(Path(__file__)),
    )


def cpu_time():
    child = getrusage(RUSAGE_CHILDREN)
    return process_time() + child.ru_utime + child.ru_stime


def run(ident, original, work):
    if os.sched_getaffinity(0) != {LANES[ident]} or os.nice(0) < 10:
        raise ValueError("use the locked confirmation CPU at nice 10 or lower priority")
    setup = json.loads((trial.OUT / "plan.json").read_bytes())
    sources = frozen()
    if setup["source"] != sources["original"]:
        raise ValueError("the corrected candidate depends on different shared source bytes")
    receipt = next(q for q in setup["cases"] if q["id"] == ident)
    first = original / f"{ident}-{trial.METHOD}"
    previous = json.loads((first / "row.json").read_bytes())
    assert all(receipt[k] == v for k, v in previous.items() if k in receipt)
    assert previous["result"]["reason"] == "KeyError: 'final_phase_change_s'"
    case = json.loads((first / "input.json").read_bytes())
    save_json(work / "source-lock.json", sources)
    start = perf_counter(), cpu_time()
    result = v5_cavity_isolation.run(case, work / "engine")
    assert sources == frozen()
    validate_result(result)
    save_json(
        work / "row.json",
        dict(
            receipt,
            cpu=LANES[ident],
            result=result,
            method=trial.METHOD,
            worker_wall_s=perf_counter() - start[0],
            cpu_s=cpu_time() - start[1],
            first_attempt_sha256=checksum(first / "row.json"),
            corrected_source=sources,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=LANES, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    args = parser.parse_args()
    run(args.case, args.original, local_output(args.work))


if __name__ == "__main__":
    main()
