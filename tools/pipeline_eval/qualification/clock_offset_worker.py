"""Run the four locked nuisance models on the same native Graph and owners."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    if request["mode"] != "native":
        raise ValueError("complete archived native factors required")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.variants import clock_offset, robust_orbit_fit

    results = {}

    def infer(document, offer, catalogue):
        arms, held_wall = clock_offset.compare(document, offer, catalogue)
        results.update(models=arms, held_diagnostic_wall_s=held_wall)
        return arms[clock_offset.METHOD]

    with patch.object(robust_orbit_fit, "infer", infer):
        out = native.worker(request)
    out["stages"]["nuisance_backend"] = out["stages"].pop("same_exact_backend")
    out["result"]["boundary"] = clock_offset.BOUNDARY
    return out | results


if __name__ == "__main__":
    began = native._now()
    outcome = worker(json.load(sys.stdin))
    outcome["worker"] = native._elapsed(began)
    json.dump(outcome, sys.stdout, sort_keys=True, allow_nan=False)
