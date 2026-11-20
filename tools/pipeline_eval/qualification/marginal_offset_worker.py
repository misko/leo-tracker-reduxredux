"""Run an isolated native Graph receiver with a fixed component scale."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    scale = request.pop("component_sigma_hz")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.variants import marginal_offset, robust_orbit_fit

    if scale not in (0.0, marginal_offset.SIGMA_HZ):
        raise ValueError("this experiment uses only the two sealed scales")

    def fit(doc, offer, catalogue):
        return marginal_offset.infer(doc, offer, catalogue, sigma_hz=scale)

    with patch.object(robust_orbit_fit, "infer", fit):
        result = native.worker(request)
    result["result"]["boundary"] = marginal_offset.BOUNDARY
    return result


if __name__ == "__main__":
    started = native._now()
    result = worker(json.load(sys.stdin))
    result["worker"] = native._elapsed(started)
    json.dump(result, sys.stdout, sort_keys=True, allow_nan=False)
