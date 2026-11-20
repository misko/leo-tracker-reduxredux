"""Run the blind phase variant inside the frozen native Graph worker."""

import json
import sys
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native
from tools.pipeline_eval.variants import phase_capture
from tools.pipeline_eval.variants import robust_orbit_fit as exact


def worker(request):
    if request["mode"] != "native":
        raise ValueError("phase acquisition requires complete native GLRT factors")
    details = {}

    def infer(document, offer, catalogue):
        result, trace = phase_capture.infer(document, offer, catalogue)
        details.update(trace)
        return result

    with patch.object(exact, "infer", infer):
        out = native.worker(request)
    out["result"]["boundary"] = phase_capture.BOUNDARY
    out["stages"]["phase_and_joint_backend"] = out["stages"].pop("same_exact_backend")
    out["phase_evidence"] = details
    return out


if __name__ == "__main__":
    start = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(start)
    json.dump(out, sys.stdout, allow_nan=False, sort_keys=True)
