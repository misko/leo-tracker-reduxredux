"""Defer whole-catalogue phase copies inside the original discovery associations."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np


class ProjectedRows:
    """Gather full catalogue rows at requested observations before applying phase changes."""

    def __init__(self, base, changed_rows, values, counts):
        self.base = base
        self.changed_rows = changed_rows
        self.values = values
        self.counts = counts
        self.materialized = None

    def dense(self):
        if self.materialized is None:
            self.materialized = self.base.copy()
            self.materialized[self.changed_rows] = self.values
            self.counts["materialized_bytes"] += self.base.nbytes
        return self.materialized

    def __getitem__(self, index):
        if (self.materialized is None and isinstance(index, tuple) and len(index) == 2
                and isinstance(index[0], slice) and index[0] == slice(None)
                and isinstance(index[1], np.ndarray)
                and index[1].ndim == 1 and index[1].dtype.kind in "iu"):
            columns = index[1]
            selected = self.base[:, columns]
            selected[self.changed_rows] = self.values[:, columns]
            self.counts["column_requests"] += 1
            self.counts["replacement_cells"] += len(self.changed_rows) * len(columns)
            return selected
        return self.dense()[index]

    def __array__(self, dtype=None, copy=None):
        return np.asarray(self.dense(), dtype=dtype, copy=copy)


@contextmanager
def sparse_rank_projection(scan, *, expected_source_sha256):
    """Retain stock projections and masks, scoped to the supplied ranking scan."""
    from leo.analysis.localization_v3 import scan as kernel

    original = scan.shifted
    if (sha256(Path(kernel.__file__).read_bytes()).hexdigest() != expected_source_sha256
            or getattr(original, "__func__", None) is not kernel.ScanLikelihood.shifted):
        raise ValueError("Unexpected released discovery projection or caller")
    counts = dict(calls=0, fallbacks=0, previous_full_copy_bytes=0, materialized_bytes=0,
                  active_rows=0, catalogue_rows=0, shifted_cpu_s=0.0,
                  column_requests=0, replacement_cells=0)

    def shifted(base, phases, point, extra=None):
        if extra or any(type(a) is not np.ndarray or not a.flags.c_contiguous for a in base):
            counts["fallbacks"] += 1
            return original(base, phases, point, extra)
        start = process_time()
        active = np.flatnonzero(abs(phases) > 1e-9)
        if len(active):
            sky = dict(time_s=scan.sky["time_s"],
                       position_km=scan.sky["position_km"][active].copy(),
                       velocity_km_s=scan.sky["velocity_km_s"][active].copy())
            geometry = kernel.prepare_phase_geometry(sky, scan.times, phases[active])
            values = kernel.phase_linear_frequency(geometry, *scan.latlon(point))
        else:
            values = tuple(np.empty((0, plane.shape[1]), dtype=plane.dtype) for plane in base)
        counts["calls"] += 1
        counts["catalogue_rows"] += len(phases)
        counts["active_rows"] += len(active)
        counts["previous_full_copy_bytes"] += sum(a.nbytes for a in base)
        result = tuple(ProjectedRows(plane, active, replacements, counts)
                       for plane, replacements in zip(base, values, strict=True))
        counts["shifted_cpu_s"] += process_time() - start
        return result

    with patch.object(scan, "shifted", shifted):
        yield counts
