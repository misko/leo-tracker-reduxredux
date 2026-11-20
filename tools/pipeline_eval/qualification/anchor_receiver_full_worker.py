"""Run the existing verified native reader and Graph with the frozen anchor fitter."""

import json
import sys
from resource import RLIMIT_AS, setrlimit

from tools.pipeline_eval.variants import native_lean as native

BOUNDARY = "Complete native GLRT factors through streaming Graph and independent orbit anchors"


def worker(request):
    if request["mode"] != "native":
        raise ValueError("the full qualification requires complete native GLRT factors")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    started = native._now()
    from tools.pipeline_eval.variants import anchor_receiver_orbits, robust_orbit_fit

    imports = native._elapsed(started)
    original = robust_orbit_fit.infer
    try:
        robust_orbit_fit.infer = anchor_receiver_orbits.infer
        result = native.worker(request)
    finally:
        robust_orbit_fit.infer = original
    stages = result["stages"]
    stages["anchor_backend"] = stages.pop("same_exact_backend")
    stages["backend_import"] = {k: t + imports[k] for k, t in stages["backend_import"].items()}
    result["result"]["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    started = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(started)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
