"""Run either anonymous track builder with the same bounded joint orbit worker."""

import json
import sys
from resource import RLIMIT_AS, setrlimit

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    started = native._now()
    from tools.pipeline_eval.variants import joint_orbits, robust_orbit_fit

    projection = native.graph_projection
    if request["frontend"] == "sparse":
        from tools.pipeline_eval.variants.simple_tracks import projection

    def track(lanes, config):
        if request["shuffle"]:
            import numpy as np

            random = np.random.default_rng(20261119)
            lanes = {
                key: list(zip(t, random.permutation(values), strict=True))
                for key, points in sorted(lanes.items())
                for t, values in [tuple(zip(*points, strict=True))]
            }
        return projection(lanes, config)

    imports = native._elapsed(started)
    original = native.graph_projection, robust_orbit_fit.infer
    try:
        native.graph_projection, robust_orbit_fit.infer = track, joint_orbits.infer
        out = native.worker(request)
    finally:
        native.graph_projection, robust_orbit_fit.infer = original
    stages = out["stages"]
    stages["track_builder"] = stages.pop("graph")
    stages["joint_backend"] = stages.pop("same_exact_backend")
    stages["backend_import"] = {
        key: value + stages["backend_import"][key] for key, value in imports.items()
    }
    out["result"]["boundary"] = (
        f"Complete archived GLRT through {request['frontend']} tracks and the common joint fit"
    )
    return out


if __name__ == "__main__":
    started = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(started)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
