"""Two ways to choose a single initial branch for the compact v5 cavity fit."""

import sys
from pathlib import Path

from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean


def first_ranked(scan):
    return v5_core.fit_initial_nodes(scan, v5_core.ranked_initial_nodes(scan)[:1])


def one_seed(scan):
    from leo.analysis.localization_v3.discovery import fresh_discovery

    (seed,) = fresh_discovery(scan, scan.radio_sigma_hz, budget=1)
    return v5_core.fit_initial_nodes(scan, [v5_core.cold_node(scan, seed)])


METHODS = {"v5_one_seed": one_seed, "v5_first_ranked": first_ranked}


def run(case, work_dir, method):
    if method not in METHODS:
        raise ValueError(f"unknown initial assignment policy {method}")
    library = Path(work_dir) / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(
        case, work_dir, Path(__file__), worker_args=(str(library), method)
    )
    result["boundary"] = (
        "Complete archived GLRT through a single initial branch and the v5 cavity fit"
    )
    result["metrics"]["initial_policy"] = method
    return result


if __name__ == "__main__":
    request, result, library, method = sys.argv[1:]
    orbit_projector.worker(request, result, library, select_initial=METHODS[method])
