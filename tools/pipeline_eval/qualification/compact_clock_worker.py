"""Run the unchanged complete native Graph front end with the compact clock."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native

BOUNDARY = "Complete stored native GLRT factors through Graph and compact receiver clock"


def worker(request):
    if request["mode"] != "native":
        raise ValueError("the complete native factors are required")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    start = native._now()
    from tools.pipeline_eval.variants import compact_clock, robust_orbit_fit

    imported = native._elapsed(start)
    with patch.object(robust_orbit_fit, "infer", compact_clock.infer):
        result = native.worker(request)
    stages = result["stages"]
    stages["clock_backend"] = stages.pop("same_exact_backend")
    for key, value in imported.items():
        stages["backend_import"][key] += value
    result["result"]["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    started = native._now()
    outcome = worker(json.load(sys.stdin))
    outcome["worker"] = native._elapsed(started)
    json.dump(outcome, sys.stdout, sort_keys=True, allow_nan=False)
