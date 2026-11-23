"""Score one bounded block through the stock bilateral terminal reducer."""

from collections import deque
from ctypes import CDLL, c_double, c_int, c_size_t, c_void_p

import numpy as np

from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import probe_layout


BLOCK_WIDTH = 4


class ProbeBlock:
    def __init__(self, library, packed):
        grid = packed.geometry
        self.packed = packed
        self.computed = self.calls = 0
        self.call = CDLL(str(library)).regional_probe_block
        self.call.argtypes = [c_size_t] * 4 + [c_void_p] * 14 + [c_double] * 2 + [c_void_p] * 8
        self.call.restype = c_int
        if grid is None:
            raise ValueError("Regional orbit geometry is unavailable")
        base = grid.geometry
        vectors = (base.position_km, base.velocity_km_s,
                   grid.position_derivative, grid.velocity_derivative)
        additive = (base.position_norm_squared, base.position_dot_velocity,
                    grid.numerator_derivative, grid.position_dot_derivative)
        self.orbits, self.times = additive[0].shape
        shape = (self.orbits, self.times)
        if (self.orbits != len(packed.labels) or packed.last >= self.times
                or any(a.shape != (*shape, 3) for a in vectors)
                or any(a.shape != shape for a in additive)
                or any(type(a) is not np.ndarray or a.dtype != np.float64
                       or not a.flags.c_contiguous or not a.flags.aligned
                       for a in (*vectors, *additive))):
            raise ValueError("Regional orbit geometry is outside the native layout")
        self.inputs = (*vectors, *additive, packed.offset, packed.index,
                       packed.observed, packed.scale, packed.base)
        self.frame = np.empty((8, BLOCK_WIDTH))
        orbit_shape = (self.times, BLOCK_WIDTH)
        self.frequency = np.empty(orbit_shape)
        self.horizon = np.empty(orbit_shape, dtype=np.int8)
        self.derivative = np.empty(orbit_shape)
        track_shape = (len(packed.tracks), BLOCK_WIDTH)
        self.best = np.empty(track_shape)
        self.score = np.empty(track_shape)
        self.owner = np.empty(track_shape, dtype=np.int64)
        self.scratch = (self.frequency, self.horizon, self.derivative, packed.raw,
                        packed.phase, self.best, self.score, self.owner)

    def __call__(self, points):
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

        if not 0 < len(points) <= BLOCK_WIDTH:
            raise ValueError("Invalid probe block width")
        for lane, point in enumerate(points):
            lat, lon = point["latlon"]
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Invalid regional probe coordinate")
            observer = geodetic_to_ecef_km(lat, lon, 0.)
            up = ecef_to_enu_matrix(lat, lon)[2]
            self.frame[:3, lane] = observer
            self.frame[3:6, lane] = up
            self.frame[6, lane] = observer @ observer
            self.frame[7, lane] = observer @ up
        packed = self.packed
        self.calls += 1
        status = self.call(
            len(points), len(packed.tracks), self.orbits, self.times,
            *(a.ctypes.data for a in (self.frame, *self.inputs)),
            packed.noise, np.log(packed.catalogue), *(a.ctypes.data for a in self.scratch),
        )
        if status:
            raise ValueError("Nonfinite native regional probe block")
        self.computed += len(points)
        rows = []
        for lane, point in enumerate(points):
            sums, owners = dict.fromkeys(packed.groups, 0.), {}
            for track, score, owner in zip(packed.tracks, self.score[:, lane],
                                           self.owner[:, lane], strict=True):
                sums[track["receiver"]] += float(score)
                owners[track["key"]] = None if owner < 0 else int(packed.labels[owner])
            rows.append(dict(point, score=sum(sums.values()) / packed.total, owners=owners,
                             receiver_scores={str(r): sums[r] / packed.counts[r] for r in packed.groups}))
        return rows


class OrderedProbeScores:
    def __init__(self, points, width_km, block, stock):
        eligible, remaining = probe_layout(points, width_km)
        self.order = [points[i] for i in (*eligible, *remaining)]
        self.fence = len(eligible)
        self.block, self.stock = block, stock
        self.cursor = 0
        self.pending = deque()
        self.failed = False

    def __call__(self, point):
        if self.cursor >= len(self.order) or self.order[self.cursor] is not point:
            raise ValueError("Unexpected terminal probe order")
        start = self.cursor
        self.cursor += 1
        if not self.pending and not self.failed:
            stop = self.fence if start < self.fence else len(self.order)
            try:
                self.pending.extend(self.block(self.order[start:min(start + BLOCK_WIDTH, stop)]))
            except ValueError:
                # An invalid speculative lane cannot change an earlier scalar decision.
                self.failed = True
        return self.stock(dict(point)) if self.failed else self.pending.popleft()
