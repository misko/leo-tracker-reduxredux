"""Profile offered and halo positions on one authenticated native Graph."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.qualification import native_clock_model_worker as frontend
    from tools.pipeline_eval.variants import joint_clock_model as smooth
    from tools.pipeline_eval.variants import region_halo

    original = smooth.infer
    receipt = {}

    def infer(document, offer, catalogue, *, clock=True):
        started = native._now()
        initial = original(document, offer, catalogue, clock=clock)
        receipt["initial"] = initial
        receipt["initial_fit_time"] = native._elapsed(started)
        contexts = {}
        refine = smooth.refine

        def capture(rows, start, tile, region, half, arm, *, clock):
            fit, diag = refine(rows, start, tile, region, half, arm, clock=clock)
            contexts[arm] = rows, tile, region, fit
            return fit, diag

        wider = dict(offer, id=offer["id"] + "-halo", width_km=region_halo.HALO_WIDTH_KM)
        started = native._now()
        with patch.object(smooth, "refine", capture):
            halo = original(document, wider, catalogue, clock=clock)
        receipt["halo_fit_time"] = native._elapsed(started)
        receipt["halo"] = halo
        if halo["status"] != "ok" or len(contexts) != 2:
            decision = dict(state="ambiguous", reason="halo_did_not_publish")
        else:
            started = native._now()
            folded = region_halo.folds(contexts)
            receipt["orbit_folds"] = folded
            senses = [p for v in folded.values() for p in (v["full"], *v["folds"]) if p is not None]
            decision = region_halo.vote(senses, offer["width_km"] / 2)
            receipt["fold_time"] = native._elapsed(started)
        receipt["halo_vote"] = decision
        return region_halo.qualify(initial, decision)

    with patch.object(smooth, "infer", infer):
        output = frontend.worker(request)
    output["result"]["boundary"] = region_halo.BOUNDARY
    return output | receipt


if __name__ == "__main__":
    started = native._now()
    output = worker(json.load(sys.stdin))
    output["worker"] = native._elapsed(started)
    json.dump(output, sys.stdout, sort_keys=True, allow_nan=False)
