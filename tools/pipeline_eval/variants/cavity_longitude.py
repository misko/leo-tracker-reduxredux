"""Longitude-safe versions of the cavity receiver's existing local charts."""

from math import cos, isfinite, radians

import numpy as np

MAX_LATITUDE_DEG = 80.0
MAX_WIDTH_KM = 25.0
MAX_CENTER_SEPARATION_KM = 150.0


def longitude(degrees):
    """Preserve the original arithmetic on the open chart; wrap at its seam."""
    if -180.0 <= degrees < 180.0:
        return degrees
    return (degrees + 180.0) % 360.0 - 180.0


def local_latlon(center, scale, local):
    latitude = center[0] + local[1] / 111.0
    return latitude, longitude(center[1] + local[0] / scale)


def local_native_point(center, scale, latlon):
    return np.array(
        [
            longitude(latlon[1] - center[1]) * scale,
            (latlon[0] - center[0]) * 111.0,
        ]
    )


def validate_geometry(tile, screen, width_km):
    """Limit the inherited local linear chart without bounding absolute longitude."""
    for center in (tile, screen):
        if not (
            len(center) == 2
            and all(isfinite(value) for value in center)
            and abs(center[0]) <= MAX_LATITUDE_DEG
            and abs(center[1]) <= 180.0
        ):
            raise ValueError("finite nonpolar tile and screen coordinates required")
    if not 0 < width_km <= MAX_WIDTH_KM:
        raise ValueError("the longitude variant supports tiles up to 25 km wide")
    east, north = local_native_point(screen, 111.32 * cos(radians(screen[0])), tile)
    if east * east + north * north > MAX_CENTER_SEPARATION_KM**2:
        raise ValueError("the tile and broad screen must be within 150 chart km")
