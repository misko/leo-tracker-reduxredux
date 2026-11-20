"""Compose the three measured v5 exception guards around one compact fit."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    v5_cavity_isolation,
    v5_lean,
    v5_orbit_domain,
    v5_previous_orbit,
    v5_secant_fit,
)

METHOD = "v5_causal_orbit_fit"
BOUNDARY = "Complete capture-era native factors to compact secant with three guarded repairs"
RECEIPTS = ("orbit_support", "previous_orbit", "optional_cavity")


def compose(layers, base):
    """Bind the frozen workers' common secant port in process-local LIFO order."""

    def call(index, request, result, library, mode):
        if mode != "secant":
            raise ValueError("composed orbit fit requires the measured compact secant objective")
        if index == len(layers):
            return base(request, result, library, mode)

        def next_worker(request, result, library, mode):
            return call(index + 1, request, result, library, mode)

        with patch.object(v5_secant_fit, "worker", next_worker):
            return layers[index](request, result, library)

    return lambda request, result, library: call(0, request, result, library, "secant")


def worker(request, result, library):
    execute = compose(
        (v5_orbit_domain.worker, v5_previous_orbit.worker, v5_cavity_isolation.worker),
        v5_secant_fit.worker,
    )
    execute(request, result, library)
    path = Path(result)
    report = json.loads(path.read_bytes())
    if any(key not in report["metrics"] for key in RECEIPTS):
        raise ValueError("composed position response lacks a measured guard receipt")
    report["boundary"] = BOUNDARY
    save_json(path, report)


def run(case, work_dir):
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    library = work / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(
        case, work, Path(__file__), worker_args=(str(library.resolve()),)
    )
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
