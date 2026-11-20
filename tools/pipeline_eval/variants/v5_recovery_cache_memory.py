"""Bound dirty cache while retaining the existing byte-identical orbit scratch bank."""

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import (
    orbit_projector,
    v5_lean,
    v5_nomination_memory,
    v5_stream_recovery,
)

METHOD = "v5_recovery_cache_memory"
BOUNDARY = "Complete compact v5 with bounded dirty cache during orbit scratch writes"
WRITE_WINDOW_BYTES = 8 * 1024**2


@contextmanager
def bounded_scratch_cache(trace=None):
    append, receipt = v5_stream_recovery.OrbitRows.append, v5_stream_recovery.receipt
    page = os.sysconf("SC_PAGE_SIZE")
    synced = {}
    metrics = dict(syncs=0, max_sync_range_bytes=0, advised_bytes=0)

    def flush(row, *, final=False):
        start = synced.get(row, 0)
        end = row.nbytes
        if end == start or (not final and end - start < WRITE_WINDOW_BYTES):
            return
        end -= end % page
        number = metrics["syncs"] + 1
        if trace is not None:
            trace("enter", number)
        fd = row.file.fileno()
        os.fdatasync(fd)
        if end > start:
            os.posix_fadvise(fd, start, end - start, os.POSIX_FADV_DONTNEED)
        synced[row] = end
        metrics["syncs"] = number
        metrics["advised_bytes"] += end - start
        metrics["max_sync_range_bytes"] = max(metrics["max_sync_range_bytes"], end - start)
        if trace is not None:
            trace("leave", number)

    def append_bounded(row, values):
        append(row, values)
        flush(row)

    def receipt_bounded(position, velocity, usable=None):
        flush(position, final=True)
        flush(velocity, final=True)
        return receipt(position, velocity, usable)

    with (
        patch.object(v5_stream_recovery.OrbitRows, "append", append_bounded),
        patch.object(v5_stream_recovery, "receipt", receipt_bounded),
    ):
        yield metrics


def measured_worker(original, request, result, library, trace=None):
    with bounded_scratch_cache(trace) as usage:
        original(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["metrics"]["recovery_cache_memory"] = usage
    value["boundary"] = BOUNDARY
    save_json(path, value)


def worker(request, result, library):
    measured_worker(v5_nomination_memory.worker, request, result, library)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
