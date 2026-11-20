"""Measure the soft position and old joint receiver on one native Graph."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    if request["mode"] != "native":
        raise ValueError("complete archived native factors required")
    cap = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (cap, cap))
    from tools.pipeline_eval.variants import joint_orbits, robust_orbit_fit, soft_identity

    companion = {}

    def infer(document, offer, catalogue):
        started = native._now()
        position = soft_identity.infer(document, offer, catalogue)
        companion["soft_backend"] = native._elapsed(started)
        started = native._now()
        companion["control_result"] = joint_orbits.infer(document, offer, catalogue)
        companion["control_backend"] = native._elapsed(started)
        return position

    with patch.object(robust_orbit_fit, "infer", infer):
        out = native.worker(request)
    out["stages"]["compared_backends"] = out["stages"].pop("same_exact_backend")
    out["result"]["boundary"] = soft_identity.BOUNDARY
    return out | companion


if __name__ == "__main__":
    began = native._now()
    row = worker(json.load(sys.stdin))
    row["worker"] = native._elapsed(began)
    json.dump(row, sys.stdout, sort_keys=True, allow_nan=False)
