"""Run the sealed compact composition with row-major residual and reassociation screens."""

import json
import sys
from pathlib import Path

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import nomination_memory_worker
from tools.pipeline_eval.variants import v5_recovery_cache_memory as cache
from tools.pipeline_eval.variants import v5_recovery_reads as tiled


def worker(request, result, library):
    before = tiled.process_io()
    with tiled.recovery_reads() as measurements:
        cache.measured_worker(nomination_memory_worker.worker, request, result, library)
    after = tiled.process_io()
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["metrics"]["recovery_reads"] = {
        "sweeps": measurements,
        "worker_io": {name: after[name] - before[name] for name in after},
    }
    value["boundary"] = tiled.BOUNDARY
    save_json(path, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
