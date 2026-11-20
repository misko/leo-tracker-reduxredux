"""Reuse exact SGP4 cells while recomputing each requested prefix validity filter."""

from collections import defaultdict
from time import perf_counter, process_time

import numpy as np
from sgp4.api import SatrecArray


class KnotBank:
    def __init__(self, capacity):
        self.capacity = capacity
        self.rows = {}
        self.used = np.empty(0, dtype=int)
        self.good = np.empty((0, capacity), dtype=bool)
        self.positions = np.empty((0, capacity, 3), dtype=float)
        self.velocities = np.empty_like(self.positions)

    def indices(self, satellites):
        old = len(self.rows)
        ids = [self.rows.setdefault(s.satnum, len(self.rows)) for s in satellites]
        added = len(self.rows) - old
        if added:
            self.used = np.r_[self.used, np.zeros(added, dtype=int)]
            self.good = np.concatenate((self.good, np.empty((added, self.capacity), dtype=bool)))
            self.positions = np.concatenate((self.positions, np.empty((added, self.capacity, 3))))
            self.velocities = np.concatenate((self.velocities, np.empty((added, self.capacity, 3))))
        return np.asarray(ids, dtype=int)

    @property
    def size(self):
        return self.used.nbytes + self.good.nbytes + self.positions.nbytes + self.velocities.nbytes


class EphemerisReuse:
    """A cache bound to one causal catalogue, anchor, and the pinned coarse/fine layouts."""

    def __init__(self, grid):
        self.grid = grid
        self.stock = grid._valid_states
        self.anchor = None
        self.keys = {}
        self.banks = {
            step: KnotBank(len(grid._knots(360.0, step)))
            for step in (grid.COARSE_ORBIT_STEP_S, grid.FINE_ORBIT_STEP_S)
        }
        self.cells = self.requests = self.exact_fallbacks = 0
        self.wall_s = self.cpu_s = 0.0

    def sums(self):
        return dict(
            cells=self.cells,
            requested_cells=self.requests,
            exact_fallbacks=self.exact_fallbacks,
            cpu_s=self.cpu_s,
            wall_s=self.wall_s,
            retained_bytes=sum(bank.size for bank in self.banks.values()),
        )

    def fallback(self, satellites, anchor, knots):
        self.exact_fallbacks += 1
        self.cells += len(satellites) * len(knots)
        return self.stock(satellites, anchor, knots)

    def __call__(self, satellites, anchor, knots):
        wall, cpu = perf_counter(), process_time()
        try:
            return self.evaluate(satellites, anchor, knots)
        finally:
            self.wall_s += perf_counter() - wall
            self.cpu_s += process_time() - cpu

    def evaluate(self, satellites, anchor, knots):
        count = len(knots)
        self.requests += len(satellites) * count
        if count < 2 or not satellites:
            return self.fallback(satellites, anchor, knots)
        step = knots[1] - knots[0]
        bank = self.banks.get(step)
        if (
            bank is None
            or count > bank.capacity
            or self.anchor not in (None, anchor)
            or not np.array_equal(knots, -self.grid.PHASE_LIMIT_S + step * np.arange(count))
            or len({s.satnum for s in satellites}) != len(satellites)
            or any(self.keys.get(s.satnum, s) is not s for s in satellites)
        ):
            return self.fallback(satellites, anchor, knots)
        self.anchor = anchor
        self.keys.update((s.satnum, s) for s in satellites)
        indices = bank.indices(satellites)
        absent = defaultdict(list)
        for request_row, index in enumerate(indices):
            if bank.used[index] < count:
                absent[bank.used[index]].append(request_row)
        for used, rows in absent.items():
            ids = indices[rows]
            time = slice(used, count)
            model = SatrecArray([satellites[i] for i in rows])
            g = self.grid
            jd, fr = g.julian_day_from_utc_ns(anchor + np.rint(knots[time] * 1e9).astype(np.int64))
            err, p, v = model.sgp4(jd, fr)
            minimum = g._POLAR_RADIUS_KM + g.MINIMUM_PLAUSIBLE_ALTITUDE_KM
            good = (
                (err == 0)
                & np.isfinite(p).all(axis=-1)
                & np.isfinite(v).all(axis=-1)
                & (np.linalg.norm(p, axis=-1) >= minimum)
            )
            with np.errstate(invalid="ignore"):
                p, v = g.teme_to_ecef(p, v, g.greenwich_mean_sidereal_time_rad(jd, fr))
            bank.positions[ids, time], bank.velocities[ids, time] = p, v
            bank.good[ids, time] = good
            bank.used[ids] = count
            self.cells += len(ids) * (count - int(used))
        okay = bank.good[indices, :count].all(axis=1)
        keep = indices[okay]
        return (
            tuple(s for s, valid in zip(satellites, okay, strict=True) if valid),
            bank.positions[keep, :count],
            bank.velocities[keep, :count],
        )
