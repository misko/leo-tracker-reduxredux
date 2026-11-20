"""Run the frozen anonymous-track receivers on an isolated native detector packet."""

import json
import sys
from hashlib import sha256
from pathlib import Path
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(payload):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.variants import (
        joint_clock_model,
        joint_orbits,
        robust_orbit_fit,
        train_update,
    )

    method = payload["method"]
    request = payload["request"]
    assert set(payload) == {"method", "request"}
    assert request["mode"] == "native"
    observed = []

    def clock(observation, offer, catalogue):
        observed.append(observation)
        return joint_clock_model.infer(observation, offer, catalogue)

    def fixed(observation, offer, catalogue):
        with patch.object(joint_orbits, "solve", train_update.solve):
            return joint_orbits.infer(observation, offer, catalogue)

    backend = {
        "native_joint_clock_model": clock,
        "native_joint_orbits": joint_orbits.infer,
        train_update.METHOD: fixed,
    }[method]
    with patch.object(robust_orbit_fit, "infer", backend):
        original = native.worker(request)
    if method != "native_joint_clock_model":
        return original
    # Exercise the actual prepared observation port on the identical anonymous observations.
    raw = json.dumps(observed[0], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    path = Path("/tmp/anonymous-observations.json")
    path.write_bytes(raw)
    prepared = dict(
        request, mode="prepared", observation=dict(path=str(path), sha256=sha256(raw).hexdigest())
    )
    with patch.object(robust_orbit_fit, "infer", joint_clock_model.infer):
        control = native.worker(prepared)
    fields = ("arms", "status", "reason")
    return dict(
        original,
        prepared_result=control["result"],
        prepared_stages=control["stages"],
        prepared_projection_sha256=control["observation_sha256"],
        prepared_equal=(
            original["observation_sha256"] == control["observation_sha256"]
            and all(original["result"][k] == control["result"][k] for k in fields)
        ),
    )


if __name__ == "__main__":
    json.dump(worker(json.load(sys.stdin)), sys.stdout, allow_nan=False)
