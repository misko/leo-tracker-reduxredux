from types import SimpleNamespace

import numpy as np
from matplotlib.transforms import Bbox

from reports.ALGO08.v3.orbit_gray_layout_trial import explain_gray, source_geometry


def test_gray_diagnostic_counts_without_replacing_strict_support():
    original = np.full((12, 24, 3), 255, dtype=np.uint8)
    peer = original.copy()
    original[3, 3] = original[6, 10] = original[6, 16] = [155, 155, 155]
    peer[1, 3] = [154, 154, 154]
    peer[6, 10] = [153, 157, 161]
    assert explain_gray(original, peer) == dict(pixels=3, misses=3, outside_crop=1, nearby_tint=1, unresolved=1)


def test_ordinary_display_geometry_converts_the_origin_and_keeps_fractional_bounds():
    axes = [SimpleNamespace(bbox=Bbox.from_extents(168, 100.25, 2328, 350.75))]
    chart = SimpleNamespace(axes=axes, bbox=Bbox.from_bounds(0, 0, 2400, 3172.5))
    assert source_geometry(chart) == (3172, [(168, 2821.25, 2160, 250.5)])
