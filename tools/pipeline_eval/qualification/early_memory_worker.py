"""Measure early track-column projection and complete per-process memory."""

import json
import sys
from collections import Counter
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from threading import Event, Thread
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import stream_recovery_worker
from tools.pipeline_eval.qualification.working_memory_worker import fingerprint, rss
from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_track_projection

COUNTERS = ("RssAnon", "RssFile", "RssShmem", "VmRSS")


def memory_categories():
    status = Path("/proc/self/status").read_text()
    return {
        k: int(v.split()[0])
        for k, v in (line.split(":", 1) for line in status.splitlines())
        if k in COUNTERS
    }


def worker(request, result, library, mode):
    from leo.analysis.localization_v3 import history_policy

    project = orbit_projector.Projector.evaluate
    receipts, active_stage = {}, None
    maximum = {key: 0 for key in COUNTERS}
    at_peak = {key: 0 for key in COUNTERS}
    count = 0
    stop = Event()

    def sample():
        nonlocal at_peak, count
        while True:
            observed = memory_categories()
            for key in maximum:
                maximum[key] = max(maximum[key], observed[key])
            if observed["VmRSS"] > at_peak["VmRSS"]:
                at_peak = observed
            count += 1
            if stop.wait(0.025):
                return

    @wraps(project)
    def evaluate(self, stencil, *args, **kwargs):
        if active_stage:
            shape = len(stencil.positions) * stencil.index.shape[-1]
            active_stage["calls"] += 1
            active_stage["cells"] += shape
            active_stage["largest_projection_bytes"] = max(
                active_stage["largest_projection_bytes"], 24 * shape
            )
        return project(self, stencil, *args, **kwargs)

    def observe(name, operation):
        @wraps(operation)
        def measured(*args, **kwargs):
            nonlocal active_stage
            old = active_stage
            stage = Counter()
            active_stage = stage
            before, before_resident = rss(), memory_categories()
            wall, cpu = perf_counter(), process_time()
            try:
                value = operation(*args, **kwargs)
            finally:
                active_stage = old
            receipts[name] = dict(
                before=before,
                after=rss(),
                before_categories=before_resident,
                after_categories=memory_categories(),
                cpu_s=process_time() - cpu,
                wall_s=perf_counter() - wall,
                projections=dict(stage),
                decision_sha256=fingerprint(value),
            )
            return value

        return measured

    sampler = Thread(target=sample, daemon=True)
    sampler.start()
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(orbit_projector.Projector, "evaluate", evaluate))
            policy = (
                stack.enter_context(v5_track_projection.track_projection())
                if mode == "track"
                else {}
            )
            stack.enter_context(
                patch.object(
                    v5_core,
                    "ranked_initial_nodes",
                    observe("ranked_initial", v5_core.ranked_initial_nodes),
                )
            )
            stack.enter_context(
                patch.object(
                    history_policy,
                    "confidence_for",
                    observe("family_confidence", history_policy.confidence_for),
                )
            )
            stream_recovery_worker.worker(request, result, library, "control")
    finally:
        stop.set()
        sampler.join()

    path = Path(result)
    value = json.loads(path.read_bytes())
    value["metrics"]["early_memory"] = dict(
        stages=receipts,
        policy=dict(policy),
        samples=count,
        interval_s=0.025,
        independent_sample_max_kib=maximum,
        categories_at_max_sample_kib=at_peak,
        whole_worker=rss(),
    )
    if mode == "track":
        value["boundary"] = v5_track_projection.BOUNDARY
    save_json(path, value)


if __name__ == "__main__":
    worker(*sys.argv[1:])
