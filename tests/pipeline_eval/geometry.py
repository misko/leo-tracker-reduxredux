from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
from sgp4.api import SatrecArray

from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import element_line_checksum

DAY_NS = 86_400 * 10**9
ANCHOR = int(datetime(2026, 1, 5, tzinfo=UTC).timestamp()) * 10**9


def tle(number, day, node=122.0, phase=67.0, inclination=87.0, motion=15.1):
    line1 = f"1 {number:05d}U 26001A   26{day:012.8f}  .00000000  00000-0  00000-0 0  999"
    line2 = (
        f"2 {number:05d} {inclination:8.4f} {node:8.4f} 0005000"
        f"   0.0000 {phase:8.4f} {motion:11.8f}    1"
    )
    return "".join(f"{line}{element_line_checksum(line)}\n" for line in (line1, line2))


def observation():
    return SimpleNamespace(
        anchor_utc_ns=ANCHOR,
        cutoff_utc_ns=ANCHOR - 10**9,
        catalog_timestamp_ns=ANCHOR - DAY_NS // 4,
        duration_s=240.0,
        tracks=(),
    )


def direct_states(catalogue, times):
    julian, fraction = julian_day_from_utc_ns(ANCHOR + np.rint(times * 1e9).astype(np.int64))
    codes, position, velocity = SatrecArray(catalogue.satellites).sgp4(julian, fraction)
    assert not codes.any()
    return teme_to_ecef(position, velocity, greenwich_mean_sidereal_time_rad(julian, fraction))
