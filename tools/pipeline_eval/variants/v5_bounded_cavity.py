"""Apply bounded working sets to the five-refresh secant receiver through its cavity decision."""

import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.variants import (
    history_stream_prep,
    orbit_projector,
    prep_stream_sky,
    v5_family_memory,
    v5_lean,
    v5_nomination_memory,
    v5_secant_fit,
    v5_signed_context_memory,
    v5_sparse_discovery,
    v5_stream_prepare,
    v5_tiled_salvage,
    v5_track_projection,
)

METHOD = "v5_bounded_cavity"


def worker(request, result, library):
    from leo.analysis.localization_v3 import position

    native = v5_lean._read(request)["job"]["native_input"]
    with ExitStack() as stack:
        for context in (
            v5_stream_prepare.stream_preparation(native),
            prep_stream_sky.prepared_sky(),
            history_stream_prep.history_cache(),
            v5_track_projection.track_projection(),
            v5_sparse_discovery.discovery_diagnostics(),
            v5_tiled_salvage.tiled_salvage(),
            v5_family_memory.family_widths_context(),
            v5_signed_context_memory.signed_widths(),
            v5_nomination_memory.nomination_memory(),
            patch.object(position, "bounded_gauss_newton", v5_secant_fit.bounded_secant),
        ):
            stack.enter_context(context)
        orbit_projector.worker(request, result, library)


def run(case, work_dir):
    directory = Path(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
