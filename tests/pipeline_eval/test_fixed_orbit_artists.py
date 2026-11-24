"""The fixed-view route keeps native geometry, color and clipping."""

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.transforms import Affine2D
import numpy as np
import pytest

from reports.ALGO08.v3.fixed_orbit_artists import circle_path, fixed_artists, fixed_plot, fixed_scatter
from leo.presentation import orbit_plot
from tools.pipeline_eval.variants.experimental import raster_layout


def test_circle_extents_are_exact_finite_and_independent():
    path = circle_path()
    for size in (2, 8, 21, 2):
        trans = Affine2D().scale(size).translate(2, 3)
        bbox = path.get_extents(trans)
        np.testing.assert_array_equal(bbox.bounds, (2 - size / 2, 3 - size / 2, size, size))
        bbox.set_points(np.zeros((2, 2)))
    assert path.get_extents(Affine2D().scale(2).translate(2, 3)).bounds == (1, 2, 2, 2)
    with pytest.raises(ValueError):
        path.vertices[0, 0] = 42


def test_clipped_gapped_curves_and_empty_or_overlapping_scatter_match_agg():
    controls = {}
    for fixed in (False, True):
        fig = Figure(figsize=(3, 2), dpi=150)
        canvas = FigureCanvasAgg(fig)
        axis = fig.subplots()
        path = circle_path()
        colors = ("#757575", (0.7, 0.3, 0.1, 0.6))
        scatter = (lambda *args, **options: fixed_scatter(axis, path, *args, **options)) if fixed else axis.scatter
        plot = (lambda *args, **options: fixed_plot(axis, *args, **options)) if fixed else axis.plot
        axis.grid(alpha=.18)
        axis.set_axisbelow(True)
        scatter([], [], color=colors[0], s=11, alpha=.7, linewidths=0, rasterized=True)
        scatter([-.0001, .2, .2, .8, 1.0001], [0, 0, 0, .7, .2],
                color=colors[0], s=11, alpha=.7, linewidths=0, rasterized=True)
        plot(np.array([-.3, .25, np.nan, .8, 1.1]), np.array([.3, .1, np.nan, 1.2, .2]),
             color=colors[1], lw=1., alpha=.75)
        scatter([.2, .3], [0, .9], color=colors[1], s=12, linewidths=0, rasterized=True, zorder=3)
        axis.set(xlim=(0, 1), ylim=(-1, 1))
        canvas.draw()
        controls[fixed] = bytes(canvas.buffer_rgba())
    assert controls[False] == controls[True]


def test_alternate_style_or_autolimits_use_the_ordinary_renderer(monkeypatch):
    monkeypatch.setattr(orbit_plot, "Figure", raster_layout._OrbitFigure)
    opts = dict(title="", subtitle="", reuse_pixels=True, raster_layout=raster_layout)
    with fixed_artists([], alias_period_hz=None, **opts) as calls:
        assert calls is None and orbit_plot.Figure is raster_layout._OrbitFigure
    with mpl.rc_context({"scatter.marker": "s"}):
        with fixed_artists([], alias_period_hz=100.0, **opts) as calls:
            assert calls is None and orbit_plot.Figure is raster_layout._OrbitFigure
