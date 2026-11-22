"""Opt-in longitude wrapping for discovery and exterior probes."""

from contextlib import contextmanager
from math import remainder
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v3.scan import ScanLikelihood


def _longitude(degrees):
    if -180.0 <= degrees <= 180.0:
        return degrees
    return remainder(degrees, 360.0)


def _latlon(method):
    def latlon(owner, local):
        latitude, longitude = method(owner, local)
        return latitude, _longitude(longitude)

    return latlon


def _native_point(region, scan, local):
    latitude, longitude = region.latlon(local)
    return np.array(
        [_longitude(longitude - scan.center[1]) * scan.scale, (latitude - scan.center[0]) * 111.0]
    )


@contextmanager
def longitude_chart():
    """Use the periodic chart within a dedicated experimental inference process."""
    with (
        patch.object(SearchRegion, "latlon", _latlon(SearchRegion.latlon)),
        patch.object(SearchRegion, "native_point", _native_point),
        patch.object(ScanLikelihood, "latlon", _latlon(ScanLikelihood.latlon)),
    ):
        yield
