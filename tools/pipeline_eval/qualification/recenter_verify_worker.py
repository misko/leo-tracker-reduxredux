"""Run both recenter fits inside one capped native Graph worker."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    started = native._now()
    from tools.pipeline_eval.qualification import native_clock_model_worker as clock
    from tools.pipeline_eval.variants import joint_clock_model, recenter_verify

    imported = native._elapsed(started)
    inference = joint_clock_model.infer
    evidence = {}

    def both(document, offer, catalogue, *, clock=True):
        start = native._now()
        first = inference(document, offer, catalogue, clock=clock)
        evidence["first"] = first
        evidence["first_fit"] = native._elapsed(start)

        def expanded(verification_offer):
            start = native._now()
            result = inference(document, verification_offer, catalogue, clock=clock)
            evidence["verification_fit"] = native._elapsed(start)
            return result

        final, evidence["verification"] = recenter_verify.verify(first, offer, expanded)
        return final

    with patch.object(joint_clock_model, "infer", both):
        out = clock.worker(request)
    out["result"]["boundary"] = recenter_verify.BOUNDARY
    stages = out["stages"]
    stages["backend_import"] = {
        key: val + stages["backend_import"][key] for key, val in imported.items()
    }
    for stage in ("first_fit", "verification_fit"):
        if stage in evidence:
            stages[stage] = evidence.pop(stage)
    return out | evidence


if __name__ == "__main__":
    started = native._now()
    result = worker(json.load(sys.stdin))
    result["worker"] = native._elapsed(started)
    json.dump(result, sys.stdout, sort_keys=True, allow_nan=False)
