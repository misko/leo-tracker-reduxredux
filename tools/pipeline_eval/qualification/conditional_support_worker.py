"""Run the withheld-phase rescue behind the frozen native Graph boundary."""

import json
import sys
from unittest.mock import patch

from tools.pipeline_eval.variants import conditional_support_recovery as recovery
from tools.pipeline_eval.variants import native_lean as native
from tools.pipeline_eval.variants import robust_orbit_fit as exact


def worker(packet):
    if packet["mode"] != "native":
        raise ValueError("complete native factors required")
    detail = {}

    def fit(document, offer, catalogue):
        result, trace = recovery.infer(document, offer, catalogue)
        detail.update(trace)
        return result

    with patch.object(exact, "infer", fit):
        out = native.worker(packet)
    out["result"]["boundary"] = recovery.BOUNDARY
    out["stages"]["conditional_backend"] = out["stages"].pop("same_exact_backend")
    out["recovery"] = detail
    return out


if __name__ == "__main__":
    start = native._now()
    result = worker(json.load(sys.stdin))
    result["worker"] = native._elapsed(start)
    json.dump(result, sys.stdout, sort_keys=True, allow_nan=False)
