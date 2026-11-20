"""Graft the causal cavity RF preflight onto the original matched aligned finish."""

import json
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    compact_finish,
    late_preflight,
    orbit_projector,
    v5_armijo_aligned_finish,
    v5_lean,
)

METHOD = "v5_late_rf_preflight"
BOUNDARY = "Stored native factors through aligned compact v5 with RF-only late preflight"


def worker(request, target, library):
    from leo.analysis.localization_v3 import reassociation_context

    stock = compact_finish.finish
    metrics = {}

    def finish(archive, identities, prepared, scan, cavity, stage_s):
        started = perf_counter()
        try:
            features = late_preflight.rf_rows(cavity["policy_arms"])
        except (KeyError, TypeError):
            features = {}
        proceed, reason, families = late_preflight.preflight(features)
        metrics.update(
            run=proceed, reason=reason, plausible=families, wall_s=perf_counter() - started
        )
        stage_s["late_rf_preflight"] = metrics["wall_s"]
        # Empty ranking uses the original validated no-target and no-fit fallbacks.
        rank = reassociation_context.rank_families if proceed else lambda _: ([], [])
        with patch.object(reassociation_context, "rank_families", rank):
            return stock(archive, identities, prepared, scan, cavity, stage_s)

    with patch.object(compact_finish, "finish", finish):
        v5_armijo_aligned_finish.worker(request, target, library)
    result = json.loads(Path(target).read_bytes())
    if result["status"] == "ok" and not metrics:
        raise ValueError("the late receiver did not consult its cavity RF preflight")
    result["boundary"] = BOUNDARY
    result["metrics"]["late_rf_preflight"] = metrics
    save_json(Path(target), result)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
