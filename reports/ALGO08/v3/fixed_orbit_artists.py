"""Use the installed Agg artists without autoscaling a fixed-view orbit sheet."""

from contextlib import contextmanager
from functools import partial
from unittest.mock import patch

import matplotlib as mpl
from matplotlib.collections import PathCollection
from matplotlib.colors import to_rgba_array
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.transforms import IdentityTransform
import numpy as np


def circle_path():
    """Reuse the exact extent of this immutable marker at a given affine size."""
    marker = MarkerStyle("o")
    path = marker.get_path().transformed(marker.get_transform())
    get_extents = path.get_extents
    extents = {}

    def extent(transform=None, **options):
        if transform is None or not transform.is_affine or options:
            return get_extents(transform, **options)
        key = transform.get_matrix().tobytes()
        if key not in extents and len(extents) < 8:
            extents[key] = get_extents(transform)
        return extents[key].frozen() if key in extents else get_extents(transform)

    path.vertices.setflags(write=False)
    path.codes.setflags(write=False)
    path.get_extents = extent
    return path


def fixed_scatter(axis, path, x, y, *, color, s, linewidths, rasterized, alpha=None, **options):
    # orbit_plot validates every input coordinate. Its explicit styles use the
    # same fill and edge RGBA and its alias transform preserves finite peaks.
    collection = PathCollection(
        (path,), (s,), facecolors=to_rgba_array(color), edgecolors=color,
        linewidths=(linewidths,), offsets=np.column_stack((x, y)),
        offset_transform=axis.transData, alpha=alpha,
    )
    collection.set_transform(IdentityTransform())
    collection.set_rasterized(rasterized)
    collection.set(**options)
    return axis.add_collection(collection, autolim=False)


def fixed_plot(axis, x, y, *, color, lw, alpha):
    line = Line2D(x, y, color=color, linewidth=lw, alpha=alpha)
    return [axis.add_line(line)]


@contextmanager
def fixed_artists(lanes, *, title, alias_period_hz, subtitle, reuse_pixels, raster_layout):
    """Restrict the alternative artist setup to the ordinary default-style sheets."""
    from leo.presentation import orbit_plot

    figure_type = orbit_plot.Figure
    if (figure_type is not raster_layout._OrbitFigure
            or mpl.__version__ != raster_layout._QUALIFIED_MATPLOTLIB
            or not reuse_pixels or alias_period_hz is None
            or not np.isfinite(alias_period_hz) or alias_period_hz <= 0
            or any(mpl.rcParams[key] != mpl.rcParamsDefault[key]
                   for key in mpl.rcParamsDefault if key not in {"backend", "backend_fallback"})):
        yield None
        return
    path = circle_path()
    calls = {"figures": 0, "axes": 0, "curves": 0, "scatters": 0}

    class FixedOrbitFigure(figure_type):
        def subplots(self, *args, **options):
            axes = super().subplots(*args, **options)
            calls["figures"] += 1
            for axis, _ in axes:
                calls["axes"] += 1
                # The frozen caller sets both limits before its first view or
                # layout query. add_line still handles transforms and clipping.
                axis._update_line_limits = lambda line: None

                def plot(*args, axis=axis, **options):
                    calls["curves"] += 1
                    return fixed_plot(axis, *args, **options)

                def scatter(*args, axis=axis, **options):
                    calls["scatters"] += 1
                    return fixed_scatter(axis, path, *args, **options)

                axis.plot, axis.scatter = plot, scatter
            return axes

    with patch.object(orbit_plot, "Figure", FixedOrbitFigure):
        yield calls
