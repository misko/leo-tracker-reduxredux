"""Share centre projections and compact repeated association work in v5 discovery."""

import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_core, v5_lean


class SelectedRows:
    def __init__(self, rows, lookup):
        self.rows = rows
        self.lookup = lookup

    def __getitem__(self, index):
        local = self.lookup[index]
        if local < 0:
            raise ValueError("Association tried to read an excluded candidate")
        return self.rows[local]


def visible_curve(curve, index, observed, predictions, method, visible, **kwargs):
    """Keep visible rows in original order and retain the stock argmin fallback row."""
    visible = visible.copy()
    visible[0] = True
    if visible.all():
        return curve(index, observed, predictions, method, **kwargs)
    rows = np.flatnonzero(visible)
    compact = predictions[rows]
    # The original satellite-by-time grids are usually Fortran strided. Keep
    # that reduction layout when gathering a smaller candidate population.
    if predictions.flags.f_contiguous:
        compact = np.asfortranarray(compact)
    fitted = curve(index, observed, compact, method, **kwargs)
    lookup = np.full(len(visible), -1, dtype=int)
    lookup[rows] = np.arange(len(rows))
    terms = {}
    for name, values in fitted.items():
        if name in ("passing", "cost"):
            expanded = np.full(len(visible), False if name == "passing" else np.inf, values.dtype)
            expanded[rows] = values
            terms[name] = expanded
        elif name != "diagnostics":
            terms[name] = SelectedRows(values, lookup)
    terms["diagnostics"] = dict(noise_screen_pass=terms["passing"].copy())
    return terms


@contextmanager
def shared_associations(scan):
    from leo.analysis.localization_v3 import discovery

    association, curve, predictions = scan.association, scan.curve, scan.predictions
    project, explore = discovery.phase_linear_frequency, discovery.explore
    counts = dict(association_reused=0, center_projections_reused=0)
    center = tuple(scan.search_region.center)
    projected_center = None

    def frequency(grid, latitude, longitude, **kwargs):
        nonlocal projected_center
        if grid is not scan.geometry or (latitude, longitude) != center or kwargs:
            return project(grid, latitude, longitude, **kwargs)
        if projected_center is None:
            projected_center = project(grid, latitude, longitude)
            for array in projected_center:
                array.setflags(write=False)
        else:
            counts["center_projections_reused"] += 1
        return projected_center

    def associate(state, base, point, method, *, all_tracks=False):
        if all_tracks or method not in ("shared_phase", "receiver_smooth") or state["extra"]:
            return association(state, base, point, method, all_tracks=all_tracks)
        elevation = None

        def predicted(*args, **kwargs):
            nonlocal elevation
            result = predictions(*args, **kwargs)
            elevation = result[1]
            return result

        def scored(index, observed, proposed, mode, **kwargs):
            visible = elevation[:, scan.index[index]].min(axis=1) >= 0
            return visible_curve(curve, index, observed, proposed, mode, visible, **kwargs)

        with patch.object(scan, "predictions", predicted), patch.object(scan, "curve", scored):
            return association(state, base, point, method, all_tracks=all_tracks)

    def exploration(scan_arg, *args, **kwargs):
        # Frozen explore calls twice with the same unmodified objects. Scope
        # reuse to that call site and retain strong references for the comparison.
        current = scan.association
        previous = None

        def reuse(state, base, point, method, *, all_tracks=False):
            nonlocal previous
            key = (tuple(point), method, all_tracks)
            if previous and previous[0] is state and previous[1] is base and previous[2] == key:
                counts["association_reused"] += 1
                return previous[3]
            result = current(state, base, point, method, all_tracks=all_tracks)
            previous = state, base, key, result
            return result

        with patch.object(scan_arg, "association", reuse):
            return explore(scan_arg, *args, **kwargs)

    with (
        patch.object(discovery, "phase_linear_frequency", frequency),
        patch.object(discovery, "explore", exploration),
        patch.object(scan, "association", associate),
    ):
        yield counts


def initial_with_sharing(original, scan):
    with shared_associations(scan):
        return original(scan)


def worker(request, result, library):
    initial = partial(initial_with_sharing, v5_core.initial_selection)
    with patch.object(v5_core, "initial_selection", initial):
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
