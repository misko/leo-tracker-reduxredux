"""Compose the previously qualified compact v5 memory variants."""

import json
import sys
from pathlib import Path

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    v5_lean,
    v5_stream_recovery,
    v5_tiled_salvage,
    v5_track_projection,
)

METHOD = "v5_composed_memory"
BOUNDARY = "Authenticated native detections through the composed compact v5 memory path"


def worker(request, result, library):
    path = Path(result)
    with (
        v5_track_projection.track_projection() as columns,
        v5_stream_recovery.streamed_recovery(path.parent) as late,
    ):
        v5_tiled_salvage.worker(request, result, library)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"].update(track_projection=dict(columns), bounded_recovery_rows=late)
    save_json(path, value)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
