"""Run the two exact early and family working-set reductions together."""

import json
import sys
from pathlib import Path

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    v5_composed_memory,
    v5_family_memory,
    v5_lean,
    v5_sparse_discovery,
)

METHOD = "v5_compact_memory_combined"
BOUNDARY = "Complete composed compact v5 with sparse discovery and sampled family widths"


def measured_worker(original, request, result, library):
    with v5_family_memory.family_widths_context():
        v5_sparse_discovery.measured_worker(original, request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    save_json(path, value)


def worker(request, result, library):
    measured_worker(v5_composed_memory.worker, request, result, library)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
