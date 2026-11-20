"""Trace completed scratch write batches at the hard cgroup cap."""

import sys

from tools.pipeline_eval.qualification import nomination_memory_worker
from tools.pipeline_eval.variants import v5_recovery_cache_memory as cache


def trace(direction, number):
    print(f"stage: {direction} late.scratch_sync#{number}", flush=True)


if __name__ == "__main__":
    cache.measured_worker(nomination_memory_worker.worker, *sys.argv[1:], trace=trace)
