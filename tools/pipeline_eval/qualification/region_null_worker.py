"""Run the regional null and native smooth position on the same authenticated Graph."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    cap = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (cap, cap))
    from tools.pipeline_eval.qualification import native_clock_model_worker as frontend
    from tools.pipeline_eval.variants import joint_clock_model as smooth
    from tools.pipeline_eval.variants import region_null

    original = smooth.infer
    state = {}

    def combined(document, offer, catalogue, *, clock=True):
        initial = original(document, offer, catalogue, clock=clock)
        started = native._now()
        evidence = region_null.infer(document, offer, catalogue)
        state.update(initial=initial, gate=evidence, gate_time=native._elapsed(started))
        return region_null.apply(initial, evidence)

    with patch.object(smooth, "infer", combined):
        out = frontend.worker(request)
    out["result"]["boundary"] = region_null.BOUNDARY
    return out | state


if __name__ == "__main__":
    started = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(started)
    json.dump(out, sys.stdout, allow_nan=False, sort_keys=True)
