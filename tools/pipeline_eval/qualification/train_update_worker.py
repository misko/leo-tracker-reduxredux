"""Select the fixed-owner update in an isolated streaming native receiver process."""

import json
import sys
from resource import RLIMIT_AS, setrlimit

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    if request["mode"] != "native":
        raise ValueError("expected native factors")
    cap = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (cap, cap))
    start = native._now()
    from tools.pipeline_eval.variants import joint_orbits, robust_orbit_fit, train_update

    importing = native._elapsed(start)
    joint_orbits.solve = train_update.solve
    robust_orbit_fit.infer = joint_orbits.infer
    out = native.worker(request)
    out["stages"]["fixed_owner_backend"] = out["stages"].pop("same_exact_backend")
    for key, value in importing.items():
        out["stages"]["backend_import"][key] += value
    out["result"]["boundary"] = train_update.BOUNDARY
    out["worker"] = native._elapsed(start)
    return out


if __name__ == "__main__":
    json.dump(worker(json.load(sys.stdin)), sys.stdout, allow_nan=False, sort_keys=True)
