"""Check both preflight branches with a bounded fresh stored-native replay."""

import argparse
import os
from pathlib import Path
from time import perf_counter

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import late_preflight, v5_lean
from . import late_preflight_worker as candidate
from . import pruned_finish_eval as matched
from .broad_search_budget import _case, frozen_inputs
from .full_receiver_comparison import sha

ROSTER = {"DS26-0066": 11, "DS29-0082": 19}
TIMEOUT = 360


def replay(ident, output):
    if os.sched_getaffinity(0) != {ROSTER[ident]}:
        raise ValueError("use the preassigned single CPU for this branch check")
    inputs = frozen_inputs()
    case = _case(inputs[ident])
    bindings = {
        key: matched.execution_binding(inputs[key], _case(inputs[key])) for key in matched.KNOWN
    }
    matched.historical_controls(bindings)
    output = local_output(output) / ident
    output.mkdir(parents=True, exist_ok=False)
    files = {
        str(p): sha(p)
        for p in (Path(__file__), Path(candidate.__file__), Path(late_preflight.__file__))
    }
    lock = dict(
        inputs=bindings[ident],
        sources=files,
        aligned_lock_sha256=sha(matched.armijo_aligned_trial.SEAL),
        aligned_predictions_sha256=sha(matched.HISTORICAL / "positions.jsonl.gz"),
        deadline_s=TIMEOUT,
        cpu=ROSTER[ident],
    )
    save_json(output / "run-lock.json", lock)
    started = perf_counter()
    v5_lean.TIMEOUT_S = TIMEOUT
    result = candidate.run(case, output / "worker")
    validate_result(result)
    if any(sha(Path(p)) != h for p, h in files.items()):
        raise ValueError("science or wrapper changed during fresh inference")
    elapsed = perf_counter() - started
    save_json(
        output / "prediction.json",
        dict(
            id=ident,
            method=candidate.METHOD,
            **bindings[ident],
            result=result,
            worker_wall_s=elapsed,
        ),
    )
    print(ident, result["status"], round(elapsed, 3), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=ROSTER)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay(args.case, args.output)
