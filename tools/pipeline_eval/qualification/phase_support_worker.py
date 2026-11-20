"""Complete unchanged native Graph followed by the blind joint phase comparison."""

import json
import sys
from functools import partial
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(packet):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.variants import phase_support, phase_support_history, robust_orbit_fit

    policy = packet.pop("phase_support_policy")
    snapshots = packet.pop("phase_history")
    if policy not in ("fixed", "wide", "causal"):
        raise ValueError("unrecognized support policy")

    def history(satellites, document, audit):
        return phase_support_history.widths(satellites, document, snapshots, audit)

    infer = partial(phase_support.infer, policy=policy, history=history)
    with patch.object(robust_orbit_fit, "infer", infer):
        result = native.worker(packet)
    result["result"]["boundary"] = (
        "Complete native GLRT and Graph to joint causal phase-support position"
    )
    return result


if __name__ == "__main__":
    start = native._now()
    out = worker(json.load(sys.stdin))
    out["worker"] = native._elapsed(start)
    json.dump(out, sys.stdout, sort_keys=True, allow_nan=False)
