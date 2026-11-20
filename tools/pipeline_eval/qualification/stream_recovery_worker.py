"""Measure frozen compact-finish stages and exact recovery inputs."""

import json
import sys
from contextlib import ExitStack
from functools import wraps
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification.batched_salvage_eval import STAGES
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint, rss
from tools.pipeline_eval.variants import v5_armijo_aligned_finish, v5_core, v5_stream_recovery


def state_hash(arrays, mask):
    p, v = arrays
    if isinstance(p, v5_stream_recovery.EligibleRows):
        return v5_stream_recovery.receipt(p[mask], v[mask], mask)
    keys = []
    for array in arrays:
        digest = sha256()
        for start in range(0, len(mask), v5_stream_recovery.BLOCK):
            sl = slice(start, start + v5_stream_recovery.BLOCK)
            digest.update(np.ascontiguousarray(array[sl][mask[sl]]))
        keys.append(digest.hexdigest())
    return dict(
        rows=int(mask.sum()),
        knots=p.shape[1],
        scratch_bytes=0,
        position_sha256=keys[0],
        velocity_sha256=keys[1],
        usable_sha256=sha256(mask).hexdigest(),
    )


def worker(request, result, library, mode):
    stages, audit = [], {}

    def observe(name, operation, output=None):
        @wraps(operation)
        def run(*args, **kwargs):
            before = rss()
            wall, cpu = perf_counter(), process_time()
            value = operation(*args, **kwargs)
            stages.append(
                dict(
                    stage=name,
                    before=before,
                    after=rss(),
                    cpu_s=process_time() - cpu,
                    wall_s=perf_counter() - wall,
                )
            )
            if output is not None:
                audit.setdefault(name, []).append(output(value))
            return value

        return run

    def watch(stack, module, name, output=None):
        hook = observe(name, getattr(module, name), output)
        stack.enter_context(patch.object(module, name, hook))

    def propagation(value):
        p, v, usable = value
        return state_hash((p, v), usable)

    def admission(value):
        return fingerprint(
            (value["nums"], value["failures"], value["propagation"], value["eligible"])
        )

    directory = Path(result).parent
    wall, cpu = perf_counter(), process_time()
    with ExitStack() as stack:
        features = (
            stack.enter_context(v5_stream_recovery.streamed_recovery(directory))
            if mode == "stream"
            else {}
        )
        for module, names in STAGES.items():
            owner = import_module(module)
            for name in names:
                proof = (
                    propagation
                    if name == "ecef_states"
                    else fingerprint
                    if name in ("screen_candidates", "screen")
                    else None
                )
                if name == "prepare_catalogue":
                    proof = admission
                watch(stack, owner, name, proof)
        for module, name, proof in (
            (v5_core, "initial_selection", None),
            (
                import_module("leo.analysis.localization_v3.reassociation_catalogue"),
                "ecef_states",
                propagation,
            ),
            (
                import_module("leo.analysis.localization_v3.reassociation_catalogue"),
                "audit",
                fingerprint,
            ),
        ):
            watch(stack, module, name, proof)
        recovery = import_module("leo.analysis.localization_v3.conservative_recovery")
        history = import_module("leo.analysis.localization_v3.history_policy")
        stock_profile, confidence = recovery.profile, history.confidence_for
        large_profiles = []

        def profile(y, predictions, *args, **kwargs):
            if np.size(predictions) * 8 < 2**20:
                return stock_profile(y, predictions, *args, **kwargs)
            stamp = rss()
            value = stock_profile(y, predictions, *args, **kwargs)
            large_profiles.append(
                dict(
                    shape=list(predictions.shape),
                    prediction_bytes=predictions.nbytes,
                    returned_bytes=sum(v.nbytes for v in value.values()),
                    before=stamp,
                    after=rss(),
                )
            )
            return value

        stack.enter_context(patch.object(recovery, "profile", profile))
        stack.enter_context(
            patch.object(history, "confidence_for", observe("family_confidence", confidence))
        )
        v5_armijo_aligned_finish.worker(request, result, library)

    path = Path(result)
    value = json.loads(path.read_bytes())
    value["metrics"]["stream_recovery_measurement"] = dict(
        elapsed_s=perf_counter() - wall,
        cpu_s=process_time() - cpu,
        whole_worker=rss(),
        stages=stages,
        banks=audit,
        candidate=features,
        largest_conservative_profile=max(
            large_profiles, key=lambda row: row["prediction_bytes"], default=None
        ),
    )
    if mode == "stream":
        value["boundary"] = v5_stream_recovery.BOUNDARY
    save_json(path, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
