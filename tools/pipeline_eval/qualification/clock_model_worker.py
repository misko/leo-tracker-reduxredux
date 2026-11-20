"""Run one receiver from an anonymous observation and causal catalogue packet."""

import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import process_time

from ..variants import joint_clock_model, joint_orbits, robust_em, robust_orbit_fit

FIXED_CONTROL = "joint_fixed_reference"
CONTROLS = {
    module.METHOD: module for module in (joint_orbits, robust_orbit_fit, robust_em)
}
METHODS = (joint_clock_model.METHOD, FIXED_CONTROL, *CONTROLS)


def measured(packet):
    if set(packet) != {"observation", "offer", "catalogue", "method"}:
        raise ValueError("receiver requires only observations, a tile, and a causal catalogue")
    args = [packet[key] for key in ("observation", "offer", "catalogue")]
    method = packet["method"]
    start = process_time()
    if method in CONTROLS:
        result = CONTROLS[method].infer(*args)
    elif method in (FIXED_CONTROL, joint_clock_model.METHOD):
        result = joint_clock_model.infer(*args, clock=method != FIXED_CONTROL)
    else:
        raise ValueError(f"unknown receiver {method}")
    return dict(
        result=result,
        worker_cpu_s=process_time() - start,
        max_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )


if __name__ == "__main__":
    json.dump(measured(json.load(sys.stdin)), sys.stdout, allow_nan=False)
