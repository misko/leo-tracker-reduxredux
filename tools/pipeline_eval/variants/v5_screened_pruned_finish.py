"""Combine early assignment screening and eligibility-pruned aligned compact v5."""

import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.variants import (
    orbit_projector,
    v5_core,
    v5_lean,
    v5_pruned_finish,
    v5_screen_winner,
    v5_shared_search,
)

METHOD = "v5_screened_pruned_finish"
BOUNDARY = "Stored native factors through screened initial assignment and pruned aligned final v5"


def initial(scan, metrics):
    # Sharing is scoped to discovery. The subsequent screen and refits run with
    # the worker's established Armijo solver and original likelihood.
    with v5_shared_search.shared_associations(scan) as counts:
        nodes = v5_core.ranked_initial_nodes(scan)[:3]
    metrics["discovery_sharing"] = counts
    screen = {}
    selected = v5_screen_winner.screen_nodes(scan, nodes, screen)
    metrics["initial_screen"] = screen
    return selected


def worker(request, output, library):
    from tools.pipeline_eval.__main__ import save_json

    measured = {}

    def select(scan):
        return initial(scan, measured)

    with patch.object(v5_core, "initial_selection", select):
        v5_pruned_finish.worker(request, output, library)
    target = Path(output)
    result = v5_lean._read(target)
    if result["status"] == "ok" and (
        set(measured) != {"discovery_sharing", "initial_screen"}
        or not {"position_optimizer", "ordered_phase_seeds", "finish_eligibility"}
        <= result["metrics"].keys()
    ):
        raise ValueError("the complete position skipped an integrated stage")
    result["metrics"].update(measured)
    result["boundary"] = BOUNDARY
    save_json(target, result)


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
