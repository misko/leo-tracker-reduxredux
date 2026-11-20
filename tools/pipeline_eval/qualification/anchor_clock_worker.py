"""Measure both anchor final fits on one complete native Graph replay."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    if request["mode"] != "native":
        raise ValueError("the complete native factors are required")
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    start = native._now()
    from tools.pipeline_eval.variants import anchor_clock, robust_orbit_fit

    imports = native._elapsed(start)
    companion = {}

    def fit(document, offer, catalogue):
        measured = anchor_clock.paired(document, offer, catalogue)
        primary = measured.pop("result")
        companion.update(measured)
        return primary

    with patch.object(robust_orbit_fit, "infer", fit):
        result = native.worker(request)
    stages = result["stages"]
    stages["anchor_pair_backend"] = stages.pop("same_exact_backend")
    for key, value in imports.items():
        stages["backend_import"][key] += value
    result["result"]["boundary"] = (
        "Complete stored native GLRT factors through Graph and the anchor receiver clock"
    )
    return result | companion


if __name__ == "__main__":
    began = native._now()
    outcome = worker(json.load(sys.stdin))
    outcome["worker"] = native._elapsed(began)
    json.dump(outcome, sys.stdout, sort_keys=True, allow_nan=False)
