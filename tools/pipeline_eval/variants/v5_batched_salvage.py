"""Use bounded Gaussian-profile batches in the compact v5 salvage stage."""

import sys
from functools import partial
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_lean

PREDICTION_BLOCK_BYTES = 2**20


def bounded_profile(profile, observed, predicted, inverse, *args, **kwargs):
    """Return the same per-candidate arrays while limiting temporary matrices."""
    candidates = np.atleast_2d(predicted)
    if candidates.ndim != 2:
        return profile(observed, predicted, inverse, *args, **kwargs)
    row_bytes = candidates.shape[1] * candidates.dtype.itemsize
    rows_per_batch = max(1, PREDICTION_BLOCK_BYTES // max(1, row_bytes))
    count = len(candidates)
    if count <= rows_per_batch:
        return profile(observed, predicted, inverse, *args, **kwargs)

    first = profile(observed, candidates[:rows_per_batch], inverse, *args, **kwargs)
    combined = {
        key: np.empty((count, *array.shape[1:]), dtype=array.dtype) for key, array in first.items()
    }
    for key, array in first.items():
        combined[key][:rows_per_batch] = array
    for start in range(rows_per_batch, count, rows_per_batch):
        stop = min(count, start + rows_per_batch)
        rows = profile(observed, candidates[start:stop], inverse, *args, **kwargs)
        for key, array in rows.items():
            combined[key][start:stop] = array
    return combined


def worker(request, result, library):
    from leo.analysis.localization_v3 import conservative_recovery

    compare = partial(bounded_profile, conservative_recovery.profile)
    with patch.object(conservative_recovery, "profile", compare):
        compact_finish.worker(request, result, library)


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
