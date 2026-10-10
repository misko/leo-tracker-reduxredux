import runpy
from pathlib import Path

import numpy as np
import pytest

api = runpy.run_path(str(Path(__file__).with_name("causal.py")))


def rows():
    return [
        {
            "label": str(i),
            "order_ns": i * 10**9,
            "reset_group": "conditional-static",
            "arms": {
                "fitted-c": [38 + i * 0.001, -121 + i * 0.002],
                "zero-c": [38 + i * 0.002, -121],
            },
        }
        for i in range(5)
    ]


def test_prefix_causality_and_matched_arms():
    source = rows()
    assert api["fuse"](source)[:3] == api["fuse"](source[:3])
    source[-1]["arms"]["fitted-c"] = [50, 70]
    assert api["fuse"](source)[:3] == api["fuse"](source[:3])


def test_outages_resets_and_membership():
    source = rows()
    source[2]["arms"]["fitted-c"] = None
    source[3]["reset_group"] = source[4]["reset_group"] = "new-static"
    out = api["fuse"](source)
    assert out[2]["arms"]["fitted-c"]["held_age_s"] == 1
    assert out[3]["arms"]["fitted-c"]["fix_count"] == 1
    with pytest.raises(ValueError):
        api["fuse"](source[::-1])
    with pytest.raises(ValueError):
        api["fuse"](source + source[:1])


def test_chart_roundtrip_dateline_and_median_rotation_limit():
    origin = [38, 179.99]
    values = np.array([[38.01, -179.99], [38.02, 179.98]])
    np.testing.assert_allclose(
        api["unchart"](api["chart"](values, origin), origin), values, atol=1e-12
    )
    # Coordinate median is deliberately not rotation invariant; document it.
    xy = np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 2.0]])
    angle = np.pi / 4
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    assert not np.allclose(np.median(xy @ rotation.T, axis=0), np.median(xy, axis=0) @ rotation.T)
