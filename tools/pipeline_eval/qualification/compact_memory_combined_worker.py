"""Observe the combined method, including numerical and scratch recovery ports."""

import sys
from collections import Counter
from contextlib import ExitStack
from functools import partial, wraps
from unittest.mock import patch

from tools.pipeline_eval.qualification import composed_memory_worker
from tools.pipeline_eval.variants import (
    v5_compact_memory_combined,
    v5_composed_memory,
    v5_stream_recovery,
)


def worker(request, result, library):
    counts = Counter()

    def observe(operation, name):
        @wraps(operation)
        def span(*args, **kwargs):
            counts[name] += 1
            label = f"late.{name}#{counts[name]}"
            print("stage: enter " + label, flush=True)
            value = operation(*args, **kwargs)
            print("stage: leave " + label, flush=True)
            return value

        return span

    measured = partial(v5_compact_memory_combined.measured_worker, v5_composed_memory.worker)
    with ExitStack() as stack:
        stack.enter_context(patch.object(v5_composed_memory, "worker", measured))
        for name in ("stream_states", "stream_audit", "project_rows"):
            operation = observe(getattr(v5_stream_recovery, name), name)
            stack.enter_context(patch.object(v5_stream_recovery, name, operation))
        composed_memory_worker.worker(request, result, library)


if __name__ == "__main__":
    worker(*sys.argv[1:])
