"""Explicit regional-search coordinates, independent of an evaluation site."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SearchRegion:
    center: tuple[float, float]
    width_km: float = 25.

    def __post_init__(self):
        center = tuple(self.center)
        if (len(center) != 2 or not np.isfinite(center).all()
                or not -90 < center[0] < 90 or not -180 <= center[1] <= 180
                or not np.isfinite(self.width_km) or self.width_km <= 0):
            raise ValueError('Finite regional coordinates and positive width required')
        object.__setattr__(self, 'center', center)

    @property
    def half_width_km(self):
        return self.width_km / 2

    def latlon(self, local):
        return (self.center[0] + local[1] / 111.0,
                self.center[1] + local[0] / (111.32 * np.cos(np.deg2rad(self.center[0]))))

    def native_point(self, scan, local):
        latitude, longitude = self.latlon(local)
        return np.array([(longitude - scan.center[1]) * scan.scale,
                         (latitude - scan.center[0]) * 111.0])

    @property
    def grid(self):
        values = tuple(f * self.width_km for f in (-.5, -.25, 0., .25, .5))
        return tuple((e, n) for e in values for n in values)
