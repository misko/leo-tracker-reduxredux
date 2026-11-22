"""Share the exact three broad phase projections across held families."""

from collections import defaultdict
from contextlib import contextmanager
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.research.orbit_phase_geometry import FrozenOrbitBank


def held_times(context):
    """Collect the original held timestamps from each unchanged common mask."""
    base, keep = context["base"], context["keep"]
    tracks = context["scan"].tracks
    times = defaultdict(list)
    for row, i, sl in zip(base.rows, base.members, base.slices, strict=True):
        selected = keep[sl]
        if selected.any():
            times[row["candidate_index"]].append(np.asarray(tracks[i]["times"])[selected])
    for entry in context["entries"]:
        j = entry["candidate_index"]
        if j in times:
            times[j].append(np.asarray(tracks[entry["track_index"]]["times"]))
    return [np.concatenate(parts) for parts in times.values() if sum(map(len, parts)) >= 4]


class SharedPhaseGrid:
    def __init__(self, original, sky, point, means, times, metrics, *, maximum_bytes=128 * 1024**2):
        self.original, self.sky, self.point, self.metrics = original, sky, tuple(point), metrics
        self.phases = {value.tobytes(): value for value in (means, means + 0.01, means - 0.01)}
        self.tables = {}
        self.frozen = None
        self.rows = len(means)
        self.keys = np.empty(0, dtype=np.uint64)
        if times and self.rows:
            # Keep exact float64 representations, including the sign of zero.
            keys = np.concatenate([np.asarray(t, dtype=np.float64).view(np.uint64) for t in times])
            unique, counts = np.unique(keys, return_counts=True)
            self.metrics.update(held_times=len(keys), distinct_times=len(unique),
                                repeated_times=int((counts > 1).sum()))
            capacity = maximum_bytes // (3 * 2 * self.rows * np.dtype(float).itemsize)
            if len(unique) < len(keys) and len(unique) <= capacity:
                self.keys = unique
            elif np.count_nonzero(counts > 1) <= capacity:
                self.keys = unique[counts > 1]

    def tabulate(self, key):
        """Bound the temporary interpolation grids while filling the shared result."""
        if self.frozen is None:
            self.frozen = FrozenOrbitBank(self.sky)
        table = tuple(np.empty((self.rows, len(self.keys))) for _ in range(2))
        width = max(1, 131_072 // self.rows)
        for i in range(0, len(self.keys), width):
            block = slice(i, i + width)
            values = self.original(self.frozen, self.keys[block].view(np.float64), *self.point,
                                   phase_seconds=self.phases[key])
            for output, computed in zip(table, values, strict=True):
                output[:, block] = computed
        for field in table:
            field.setflags(write=False)
        self.tables[key] = table
        self.metrics["evaluated_sky_cells"] += self.rows * len(self.keys)
        self.metrics["retained_table_bytes"] += sum(a.nbytes for a in table)
        return table

    def __call__(self, bank, times, latitude, longitude, *, phase_seconds=0.0, **kwargs):
        if bank is not self.sky or (latitude, longitude) != self.point or kwargs:
            return self.original(bank, times, latitude, longitude, phase_seconds=phase_seconds, **kwargs)
        phase = np.asarray(phase_seconds, dtype=np.float64)
        if phase.shape != (self.rows,) or (key := phase.tobytes()) not in self.phases:
            return self.original(bank, times, latitude, longitude, phase_seconds=phase_seconds)
        self.metrics["sky_calls"] += 1
        self.metrics["requested_sky_cells"] += self.rows * len(times)
        clock = process_time()
        try:
            return self.project(bank, times, key)
        finally:
            self.metrics["sky_cpu_s"] += process_time() - clock

    def project(self, bank, times, key):
        if len(self.keys):
            keys = np.asarray(times, dtype=np.float64).view(np.uint64)
            columns = np.minimum(np.searchsorted(self.keys, keys), len(self.keys) - 1)
            available = self.keys[columns] == keys
            if available.any():
                table = self.tables.get(key)
                if table is None:
                    table = self.tabulate(key)
                if available.all():
                    # Full-family triangular solves keep their original layouts.
                    return tuple(np.ascontiguousarray(field[:, columns]) for field in table)
                missing = ~available
                cold = self.original(self.frozen, np.asarray(times)[missing], *self.point,
                                     phase_seconds=self.phases[key])
                self.metrics["evaluated_sky_cells"] += self.rows * int(missing.sum())
                values = tuple(np.empty((self.rows, len(times))) for _ in range(2))
                for output, reused, fresh in zip(values, table, cold, strict=True):
                    output[:, available] = reused[:, columns[available]]
                    output[:, missing] = fresh
                return values
        self.metrics["evaluated_sky_cells"] += self.rows * len(times)
        return self.original(self.frozen or bank, times, *self.point, phase_seconds=self.phases[key])


@contextmanager
def shared_projection(*, enabled=True, observe=None):
    """Keep the frozen family loop, exclusions and ranking around the projection."""
    from leo.analysis.localization_v3 import family_cavity

    nominate, project = family_cavity.nominate_families, family_cavity.phase_frequency_grid
    metrics = {}

    def run(context):
        metrics.update(sky_calls=0, requested_sky_cells=0, evaluated_sky_cells=0, sky_cpu_s=0.,
                       retained_table_bytes=0)
        start = process_time()
        scan = context["scan"]
        operation = SharedPhaseGrid(project, scan.sky, scan.search_region.latlon(context["x"]),
                                    np.asarray(context["all_means"], float), held_times(context), metrics,
                                    maximum_bytes=128 * 1024**2 if enabled else 0)
        with patch.object(family_cavity, "phase_frequency_grid", operation):
            result = nominate(context)
        metrics["nomination_cpu_s"] = process_time() - start
        if observe is not None:
            observe(result)
        return result

    with patch.object(family_cavity, "nominate_families", run):
        yield metrics
