"""Run the normal native joint solver with scalar innovations in its numerical process."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    cap = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (cap, cap))
    start = native._now()
    from tools.pipeline_eval.variants import (
        innovation_noise,
        joint_orbits,
        robust_em,
        robust_orbit_fit,
    )

    imports = native._elapsed(start)
    with (
        patch.object(robust_em, "observations", innovation_noise.observations),
        patch.object(robust_orbit_fit, "infer", joint_orbits.infer),
    ):
        out = native.worker(request)
    stages = out["stages"]
    stages["joint_backend"] = stages.pop("same_exact_backend")
    for key, value in imports.items():
        stages["backend_import"][key] += value
    out["result"]["boundary"] = (
        "Complete native GLRT to joint position with scalar noise innovations"
    )
    out["worker"] = native._elapsed(start)
    return out


if __name__ == "__main__":
    json.dump(worker(json.load(sys.stdin)), sys.stdout, allow_nan=False, sort_keys=True)
