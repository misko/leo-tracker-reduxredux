"""Keep only the diagnostics that ranked initial association can read by row."""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_composed_memory, v5_core, v5_lean

METHOD = "v5_sparse_discovery"
BOUNDARY = "Complete composed compact v5 with sparse early nomination diagnostics"


class RetainedRows:
    """Private ascending candidate index and its exact original diagnostic values."""

    def __init__(self, indices, source):
        self.indices, self.values = indices, source[indices]

    def __getitem__(self, candidate):
        index = int(np.searchsorted(self.indices, candidate))
        if index >= len(self.indices) or self.indices[index] != candidate:
            raise IndexError("discovery tried to read an unqualified diagnostic row")
        return self.values[index]


def retain_diagnostics(terms, visible):
    eligible = terms["passing"] & visible
    eligible[int(np.argmin(np.where(visible, terms["cost"], np.inf)))] = True
    indices = np.flatnonzero(eligible)
    dense, retained = 0, indices.nbytes
    for key in ("residual", "innovations"):
        array = terms[key]
        rows = RetainedRows(indices, array)
        terms[key] = rows
        dense += array.nbytes
        retained += rows.values.nbytes
    return dense, retained, len(indices)


@contextmanager
def discovery_diagnostics():
    from leo.analysis.localization_v3.scan import ScanLikelihood

    ranked = v5_core.ranked_initial_nodes
    calls = []

    def association(original, scan, state, base, point, method, *, all_tracks=False):
        if all_tracks or method not in ("shared_phase", "receiver_smooth"):
            return original(scan, state, base, point, method, all_tracks=all_tracks)
        predictions, curve = scan.predictions, scan.curve
        elevation = None
        receipt = dict(
            method=method,
            tracks=0,
            candidate_rows=0,
            retained_rows=0,
            dense_diagnostic_bytes=0,
            retained_diagnostic_bytes=0,
            largest_track_diagnostic_bytes=0,
        )

        def capture(*args, **kwargs):
            nonlocal elevation
            result = predictions(*args, **kwargs)
            elevation = result[1]
            return result

        def compress(i, y, predicted, mode, **kwargs):
            terms = curve(i, y, predicted, mode, **kwargs)
            visible = elevation[:, scan.index[i]].min(axis=1) >= 0
            dense, retained, rows = retain_diagnostics(terms, visible)
            receipt["tracks"] += 1
            receipt["candidate_rows"] += len(visible)
            receipt["retained_rows"] += rows
            receipt["dense_diagnostic_bytes"] += dense
            receipt["retained_diagnostic_bytes"] += retained
            receipt["largest_track_diagnostic_bytes"] = max(
                receipt["largest_track_diagnostic_bytes"], dense
            )
            return terms

        with patch.object(scan, "predictions", capture), patch.object(scan, "curve", compress):
            value = original(scan, state, base, point, method, all_tracks=all_tracks)
        calls.append(receipt)
        return value

    def bounded(*args, **kwargs):
        original = ScanLikelihood.association

        def retained(*args, **kwargs):
            return association(original, *args, **kwargs)

        with patch.object(ScanLikelihood, "association", retained):
            return ranked(*args, **kwargs)

    with patch.object(v5_core, "ranked_initial_nodes", bounded):
        yield calls


def measured_worker(original, request, result, library):
    with discovery_diagnostics() as usage:
        original(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"]["sparse_discovery"] = usage
    save_json(path, value)


def worker(request, result, library):
    measured_worker(v5_composed_memory.worker, request, result, library)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
