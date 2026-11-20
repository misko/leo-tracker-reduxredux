"""Run the sealed native Graph front end with the receiver-clock solver."""

import argparse
import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native

BOUNDARY = "Complete stored GLRT factors through native Graph and held receiver-clock position"


def worker(request, *, clock=True):
    if request["mode"] != "native":
        raise ValueError("only complete native factors enter this replay")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    started = native._now()
    from tools.pipeline_eval.variants import joint_clock_model, robust_orbit_fit

    imports = native._elapsed(started)

    def infer(document, offer, catalogue):
        return joint_clock_model.infer(document, offer, catalogue, clock=clock)

    with patch.object(robust_orbit_fit, "infer", infer):
        out = native.worker(request)
    stages = out["stages"]
    stages["clock_backend"] = stages.pop("same_exact_backend")
    stages["backend_import"] = {
        key: val + stages["backend_import"][key] for key, val in imports.items()
    }
    out["result"]["boundary"] = BOUNDARY
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clock-off", action="store_true")
    args = parser.parse_args()
    start = native._now()
    out = worker(json.load(sys.stdin), clock=not args.clock_off)
    out["worker"] = native._elapsed(start)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
