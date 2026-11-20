"""Run the same capped compact cavity from prior verified ordinary factors."""

import json
import os
import sys
from pathlib import Path

from tools.pipeline_eval.qualification import whole_cavity_worker as cavity
from tools.pipeline_eval.qualification import whole_memory_chain_worker as resource

CPUS, MEMORY = cavity.CPUS, cavity.MEMORY
LIMIT = 100
METHOD = "held_stock_factor_cavity"
BOUNDARY = "Fresh capped lifetime-bounded cavity from authenticated archived ordinary factors"


def launch(ident, output):
    from tools.pipeline_eval.qualification import cavity_lifetime_worker, recording_to_v5
    from tools.pipeline_eval.qualification.fractional_runtime_whole import verify_request
    from tools.pipeline_eval.qualification.full_v5_check import _sha
    from tools.pipeline_eval.variants import orbit_projector, v5_lean

    os.sched_setaffinity(0, {CPUS[0]})
    start = resource.mark("stock factor control enter")
    recording_to_v5.save(output.parent / f"{ident}-begin.json", dict(id=ident, start=start))
    output.mkdir(exist_ok=False)
    pin = json.loads((output.parent / "plan.json").read_bytes())["inputs"][ident]
    native, bound = Path(pin["stock_native_path"]), Path(pin["prior_request_path"])
    if _sha(native) != pin["native_sha256"] or _sha(bound) != pin["prior_request_sha256"]:
        raise ValueError("stock factor or blind request was modified")
    fit = output / "position"
    fit.mkdir()
    old = json.loads(bound.read_bytes())
    new = dict(old, job=dict(old["job"], output_root=str(fit)))
    verify_request(new, old, native_path=native, native_sha256=pin["native_sha256"])
    request = fit / "request.json"
    recording_to_v5.save(request, new)
    orbit_projector.compile_kernel(fit / "orbit_projector.so")
    recording_to_v5.save(
        output / "factor-input.json",
        dict(
            native_sha256=_sha(native),
            worker_request_sha256=_sha(request),
            ready=resource.mark("stock factor control input ready"),
        ),
    )
    command = [
        str(v5_lean.PYTHON),
        "-B",
        str(Path(cavity.__file__)),
        "position",
        str(output),
        str(Path(cavity_lifetime_worker.__file__)),
    ]
    env = dict(
        os.environ,
        **recording_to_v5.SINGLE_THREAD,
        PYTHONPATH=f"{v5_lean.SOURCE}:{v5_lean.RUNNER}:{recording_to_v5.REPO}",
    )
    os.execve(command[0], command, env)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "chain":
        raise ValueError("expected control entry and frozen recording")
    launch(sys.argv[2], Path(sys.argv[3]))
