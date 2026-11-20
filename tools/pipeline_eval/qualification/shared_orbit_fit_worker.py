"""Compare three anonymous fitters on a single genuine native Graph replay."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    if request["mode"] != "native":
        raise ValueError("complete native factors required")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.variants import (
        joint_orbits,
        robust_orbit_fit,
        shared_orbit_fit,
        soft_identity,
    )

    variants = {}

    def infer(document, offer, catalogue):
        for method in (shared_orbit_fit, soft_identity, joint_orbits):
            began = native._now()
            result = method.infer(document, offer, catalogue)
            variants[method.METHOD] = dict(result=result, timing=native._elapsed(began))
        return variants[shared_orbit_fit.METHOD]["result"]

    with patch.object(robust_orbit_fit, "infer", infer):
        outcome = native.worker(request)
    outcome["stages"]["compared_backends"] = outcome["stages"].pop("same_exact_backend")
    outcome["result"]["boundary"] = shared_orbit_fit.BOUNDARY
    return dict(outcome, variants=variants)


if __name__ == "__main__":
    began = native._now()
    result = worker(json.load(sys.stdin))
    result["worker"] = native._elapsed(began)
    json.dump(result, sys.stdout, sort_keys=True, allow_nan=False)
