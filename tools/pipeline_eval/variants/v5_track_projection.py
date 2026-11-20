"""Project early all-catalogue Doppler in the original track-column windows."""

import json
import sys
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from functools import wraps
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_armijo_aligned_finish, v5_core, v5_lean

METHOD = "v5_track_projection"
BOUNDARY = "Native GLRT through complete aligned compact v5 with track-column early Doppler"


class TrackColumns:
    """Share one queried track-sized C projection among the three fields."""

    def __init__(self, operation, stencil, coordinates, options, counts):
        self.operation, self.stencil = operation, stencil
        self.coordinates, self.options, self.counts = coordinates, options, counts
        self.last = None
        counts["deferred_projections"] += 1
        counts["deferred_cells"] += self.rows * self.columns
        counts["max_deferred_grid_bytes"] = max(
            counts["max_deferred_grid_bytes"], 24 * self.rows * self.columns
        )

    @property
    def rows(self):
        return len(self.stencil.positions)

    @property
    def columns(self):
        return self.stencil.index.shape[-1]

    def read(self, columns):
        if self.last is not None and np.array_equal(columns, self.last[0]):
            self.counts["shared_field_queries"] += 1
            return self.last[1]
        self.last = None
        sliced = replace(
            self.stencil,
            index=np.ascontiguousarray(self.stencil.index[..., columns]),
            fraction=np.ascontiguousarray(self.stencil.fraction[..., columns]),
        )
        values = self.operation(sliced, *self.coordinates, **self.options)
        self.counts["track_projections"] += 1
        self.counts["track_cells"] += self.rows * len(columns)
        self.counts["max_track_grid_bytes"] = max(
            self.counts["max_track_grid_bytes"], sum(a.nbytes for a in values)
        )
        self.last = columns.copy(), values
        return values


class TrackField:
    """Read full catalogue rows at original track columns, with lazy phase overlays."""

    def __init__(self, source, field, overlays=()):
        self.source, self.field = source, field
        self.overlays = list(overlays)

    @property
    def shape(self):
        return (self.source.rows, self.source.columns)

    def copy(self):
        return TrackField(self.source, self.field, self.overlays)

    def __getitem__(self, item):
        rows, columns = item
        columns = np.asarray(columns)
        if rows != slice(None) or columns.ndim != 1 or columns.dtype.kind not in "iu":
            raise IndexError("early Doppler field requires a full row and indexed column selection")
        # The frozen source's C array[:, indices] returns a new Fortran-layout
        # result. Preserve that reduction order even though C only computed this track.
        current = np.array(self.source.read(columns)[self.field], order="F", copy=True)
        for active, projected in self.overlays:
            current[active] = projected[:, columns]
        return current

    def __setitem__(self, item, value):
        active = np.asarray(item)
        if (
            not isinstance(value, TrackField)
            or active.ndim != 1
            or active.dtype.kind not in "iu"
            or value.shape != (len(active), self.source.columns)
        ):
            raise ValueError("early Doppler overlay requires indexed rows of a matching projection")
        self.overlays.append((active.copy(), value))


@contextmanager
def track_projection():
    from leo.analysis.localization_v3 import discovery, family_weighting, history_policy, scan

    counts = Counter()
    rank, confidence = v5_core.ranked_initial_nodes, history_policy.confidence_for

    def factory(operation):
        def project(stencil, *coordinates, **options):
            if not isinstance(stencil, orbit_projector.Stencil):
                return operation(stencil, *coordinates, **options)
            source = TrackColumns(operation, stencil, coordinates, options, counts)
            return tuple(TrackField(source, field) for field in range(3))

        return project

    @wraps(rank)
    def ranked(*args, **kwargs):
        with (
            patch.object(
                discovery, "phase_linear_frequency", factory(discovery.phase_linear_frequency)
            ),
            patch.object(scan, "phase_linear_frequency", factory(scan.phase_linear_frequency)),
        ):
            return rank(*args, **kwargs)

    @wraps(confidence)
    def confident(*args, **kwargs):
        with patch.object(
            family_weighting,
            "phase_linear_frequency",
            factory(family_weighting.phase_linear_frequency),
        ):
            return confidence(*args, **kwargs)

    with (
        patch.object(v5_core, "ranked_initial_nodes", ranked),
        patch.object(history_policy, "confidence_for", confident),
    ):
        yield counts


def worker(request, result, library):
    with track_projection() as counts:
        v5_armijo_aligned_finish.worker(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"]["track_projection"] = dict(counts)
    save_json(path, value)


def run(case, work_dir):
    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
