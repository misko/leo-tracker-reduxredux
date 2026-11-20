"""Run the frozen streaming front end with the frozen joint solver."""

import json
import sys
from resource import RLIMIT_AS, setrlimit

from tools.pipeline_eval.variants import native_lean as native

BOUNDARY = "Complete stored GLRT factors through streaming Graph and held joint orbit positioning"


def worker(request):
    if request["mode"] != "native":
        raise ValueError("only complete native factors enter this replay")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    started = native._now()
    from tools.pipeline_eval.variants import joint_orbits, robust_orbit_fit

    imports = native._elapsed(started)
    original = robust_orbit_fit.infer
    try:
        robust_orbit_fit.infer = joint_orbits.infer
        out = native.worker(request)
    finally:
        robust_orbit_fit.infer = original
    stages = out["stages"]
    stages["joint_backend"] = stages.pop("same_exact_backend")
    stages["backend_import"] = {
        key: val + stages["backend_import"][key] for key, val in imports.items()
    }
    out["result"]["boundary"] = BOUNDARY
    return out


if __name__ == "__main__":
    start = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(start)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
