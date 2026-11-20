"""Apply the sealed Armijo position hook to the complete compact v5 decision."""

import json
import sys
from collections import Counter
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_armijo_fit, v5_lean

BOUNDARY = "Capture-era native detector input to both Armijo compact v5 final positions"


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))
    result["boundary"] = BOUNDARY
    return result


def worker(request, target, library):
    from leo.analysis.localization_v3 import position, reassociation_context

    from tools.pipeline_eval.__main__ import save_json

    counts, stops = Counter(), Counter()
    adoption = {}
    adopt = reassociation_context.adopt_additional

    def optimize(*args, **kwargs):
        start = perf_counter()
        fit = v5_armijo_fit.bounded_armijo(*args, **kwargs)
        counts["wall_s"] += perf_counter() - start
        counts["calls"] += 1
        for key in ("evaluations", "jacobian_refreshes", "rejected_trials"):
            counts[key] += fit[key]
        stops[fit["stopped"]] += 1
        return fit

    def selected_addition(*args, **kwargs):
        result = adopt(*args, **kwargs)
        replay = result["replay"]
        decision = replay["recovery"]
        adoption.update(status=decision["status"], source=decision.get("source"))
        if "algo06" in replay:
            adoption["added_points"] = {
                arm: replay["algo06"][arm]["added_points"] for arm in v5_lean.ARMS
            }
        return result

    started, cpu = perf_counter(), process_time()
    with (
        patch.object(position, "bounded_gauss_newton", optimize),
        patch.object(reassociation_context, "adopt_additional", selected_addition),
    ):
        compact_finish.worker(request, target, library)
    result = json.loads(Path(target).read_bytes())
    if result["status"] == "ok" and (not counts["calls"] or not adoption):
        raise ValueError("Armijo optimizer or checked residual decision was bypassed")
    result["boundary"] = BOUNDARY
    result["metrics"].update(
        position_optimizer=dict(counts),
        optimizer_stops=dict(stops),
        checked_residual_addition=adoption,
        numerical_worker_wall_s=perf_counter() - started,
        numerical_worker_cpu_s=process_time() - cpu,
        numerical_worker_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )
    save_json(Path(target), result)


if __name__ == "__main__":
    worker(*sys.argv[1:])
