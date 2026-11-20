"""Execute or bypass stock late recovery using request-time Doppler curvature."""

import json
import sys
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.qualification import late_routing_sources as measured
from tools.pipeline_eval.variants import (
    late_routing,
    orbit_projector,
    v5_armijo_aligned_finish,
    v5_lean,
)

METHOD = "v5_late_curvature"
BOUNDARY = "Stored native through the aligned cavity and curvature-routed late recovery"


def worker(request, target, library):
    from leo.analysis.localization_v3 import (
        reassociation_context,
        residual_preflight,
        residual_screen,
    )
    from numpy.linalg import LinAlgError

    stock_packet = residual_preflight.preflight
    stock_screen = residual_screen.screen_candidates
    stock_rank = reassociation_context.rank_families
    metrics = {}

    def prepare(*args, **kwargs):
        packet = stock_packet(*args, **kwargs)
        started, cpu = perf_counter(), process_time()
        try:
            decision = late_routing.evaluate(packet["targets"])
        except (KeyError, ValueError, TypeError, LinAlgError):
            decision = dict(run=True, targets=[], reason="invalid RF diagnostic; retain stock")
        metrics.update(decision, wall_s=perf_counter() - started, cpu_s=process_time() - cpu)
        return packet if metrics["run"] else dict(packet, targets=[])

    def screen(packet, *args, **kwargs):
        if metrics.get("run", True):
            return stock_screen(packet, *args, **kwargs)
        if packet["targets"]:
            raise ValueError("curvature bypass cannot send targets to residual screen")
        return dict(case=packet["case"], targets=[])

    def rank(context):
        return stock_rank(context) if metrics.get("run", True) else ([], [])

    with (
        patch.object(residual_preflight, "preflight", prepare),
        patch.object(residual_screen, "screen_candidates", screen),
        patch.object(reassociation_context, "rank_families", rank),
    ):
        v5_armijo_aligned_finish.worker(request, target, library)
    result = json.loads(Path(target).read_bytes())
    if result["status"] == "ok" and not metrics:
        raise ValueError("aligned finish did not consult the curvature trigger")
    result["boundary"] = BOUNDARY
    result["metrics"]["late_curvature"] = metrics
    save_json(Path(target), result)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(
        case, directory, Path(__file__), worker_args=(str(library), str(measured.REPORT))
    )


if __name__ == "__main__":
    request, target, library, *report = sys.argv[1:]
    bound_worker = worker
    if report:
        (folder,) = report
        bound_worker = measured.measured_worker(measured.measured_sources(Path(folder)))
    bound_worker(request, target, library)
