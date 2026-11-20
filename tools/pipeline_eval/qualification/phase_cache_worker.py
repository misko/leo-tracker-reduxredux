"""Run the capped compact lifetime receiver with controlled native memo telemetry."""

import json
import sys
from pathlib import Path

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import cavity_lifetime_worker
from tools.pipeline_eval.variants import v5_phase_cache


def worker(unit, cpu, request, result, library, mode):
    with v5_phase_cache.normal_memo(mode == "memo") as stats:
        cavity_lifetime_worker.worker(unit, cpu, request, result, library, "direct")
    destination = Path(result)
    value = json.loads(destination.read_bytes())
    value["metrics"]["native_normal_memo"] = dict(stats)
    save_json(destination, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
