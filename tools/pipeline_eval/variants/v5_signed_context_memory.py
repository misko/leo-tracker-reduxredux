"""Apply the sampled causal-width inventory to the signed context as well."""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    v5_family_memory,
    v5_lean,
)
from tools.pipeline_eval.variants import (
    v5_compact_memory_combined as combined,
)

METHOD = "v5_signed_context_memory"
BOUNDARY = "Complete compact v5 with sparse discovery and sampled family and signed widths"


@contextmanager
def signed_widths():
    from leo.analysis.localization_v3 import signed_context

    with patch.object(
        signed_context, "phase_widths", v5_family_memory.width_reader(signed_context.phase_widths)
    ):
        yield


def measured_worker(composition, original, request, destination, library):
    with signed_widths():
        composition(original, request, destination, library)
    path = Path(destination)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    save_json(path, value)


def worker(request, result, library):
    measured_worker(
        combined.measured_worker, combined.v5_composed_memory.worker, request, result, library
    )


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
