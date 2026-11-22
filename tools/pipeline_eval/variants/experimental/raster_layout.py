"""Single-process experiment for the complete ALGO08 publication renderer."""

from functools import cache, partial
from unittest.mock import patch

import matplotlib as mpl
import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import AutoLocator, NullFormatter, NullLocator, ScalarFormatter

from leo.contracts.fast_standard_analysis import ALGO08V2
from leo.presentation import fast_standard_analysis as plots
from leo.presentation import orbit_plot
from tools.pipeline_eval.variants.experimental.shared_orbit_figures import render_shared

_QUALIFIED_MATPLOTLIB = "3.11.1"


class UnsupportedLayout(ValueError):
    """Use the unmodified shared-pixel figures for this packet or style."""


def _memoize_ticks(axis):
    locator = axis.get_major_locator()
    if (type(locator) is not AutoLocator
            or type(axis.get_major_formatter()) is not ScalarFormatter
            or type(axis.get_minor_locator()) is not NullLocator
            or type(axis.get_minor_formatter()) is not NullFormatter):
        return
    original = axis._update_ticks
    previous = ticks = None

    def update():
        nonlocal previous, ticks
        # Shared locators read the lead axis's tick space. The tick artists
        # keep their live transforms when layout moves an axis without
        # changing its limits or automatic tick count.
        key = (tuple(axis.get_view_interval()), locator.axis.get_tick_space())
        if key != previous:
            ticks = original()
            previous = key
        return ticks

    axis._update_ticks = update


class _LayoutFigure(Figure):
    def subplots(self, *args, **kwargs):
        axes = super().subplots(*args, **kwargs)
        for axis in self.axes:
            _memoize_ticks(axis.xaxis)
            _memoize_ticks(axis.yaxis)
        return axes


class _DiscardedColumn:
    def set_title(self, text, *, fontsize):
        self.title = text
        self.fontsize = fontsize

    def ignore(self, *args, **kwargs):
        pass

    scatter = grid = set_axisbelow = set_ylabel = set_xlabel = ignore


class _OrbitFigure(_LayoutFigure):
    def subplots(self, nrows=1, ncols=1, *, sharex=False, sharey=False, squeeze=True, **kwargs):
        if ncols != 2 or not sharex or not sharey or squeeze or kwargs:
            raise UnsupportedLayout("Unexpected orbit subplot request")
        spec = self.add_gridspec(nrows, ncols)
        self._discarded = []
        rows = []
        anchor = None
        for row in range(nrows):
            axis = self.add_subplot(spec[row, 0], sharex=anchor, sharey=anchor)
            if anchor is None:
                anchor = axis
            if row != nrows - 1:
                axis._label_outer_xaxis(skip_non_rectangular_axes=True)
            _memoize_ticks(axis.xaxis)
            _memoize_ticks(axis.yaxis)
            right = _DiscardedColumn()
            self._discarded.append(right)
            rows.append((axis, right))
        return np.asarray(rows, dtype=object)

    def delaxes(self, axis):
        if not isinstance(axis, _DiscardedColumn):
            super().delaxes(axis)

    def tight_layout(self, *, rect=None, pad=1.08, **kwargs):
        if rect is None or rect[0] != 0 or rect[2] != 1 or kwargs:
            raise UnsupportedLayout("Unexpected orbit layout bounds")
        axes = self.axes
        # The stock layout queries identical bounds twice before moving axes.
        # Keep the memoization local to those measurements.
        for axis in axes:
            axis.get_tightbbox = cache(axis.get_tightbbox)
        try:
            self._check_discarded_column(pad)
            super().tight_layout(rect=rect, pad=pad)
        finally:
            for axis in axes:
                del axis.get_tightbbox

    def _check_discarded_column(self, pad):
        renderer = self.canvas.get_renderer()
        left_padding = right_padding = 0
        for axis, right in zip(self.axes, self._discarded, strict=True):
            extent = axis.get_tightbbox(renderer, for_layout_only=True)
            frame = axis.bbox
            title = axis.title
            if title.get_fontsize() != right.fontsize:
                raise UnsupportedLayout("The two orbit titles have different sizes")
            text, position = title.get_text(), title.get_position()
            try:
                title.set_text(right.title)
                title.set_position((position[0], 1.0))
                discarded_title = title.get_window_extent(renderer)
            finally:
                title.set_text(text)
                title.set_position(position)
            # Both axes have the same bottom decoration. Only the left has
            # y tick labels and y offset text. A right title of greater height
            # or one that would move above its usual baseline needs both axes.
            if discarded_title.ymin < frame.ymax or discarded_title.ymax > extent.ymax:
                raise UnsupportedLayout("Discarded orbit title can change row spacing")
            left_padding = max(left_padding, frame.xmin - extent.xmin)
            right_padding = max(right_padding, extent.xmax - frame.xmax)
        # These two column widths are thrown away after layout. Check that
        # they could fit anyway, even with the left decorations on both.
        pad_pixels = pad * mpl.rcParams["font.size"] * self.dpi / 72
        if 2 * (left_padding + right_padding) + 3 * pad_pixels >= self.bbox.width:
            raise UnsupportedLayout("Two orbit columns could exceed the usable width")


def render_shared_pixels(packet, **kwargs):
    """Use the latest shared-pixel renderer as the control and fallback."""
    with patch.object(plots, "render_fast_scan_orbits", partial(render_shared, reuse_pixels=True)):
        return plots.render(packet, **kwargs)


def render_layout(packet, *, require_trial=False, **kwargs):
    """Try exact layout reuse with the frozen Matplotlib renderer and style.

    The figure factories are scoped to this serial experiment. Integration
    into a concurrent renderer would require explicit factory injection.
    """
    try:
        default_style = all(
            mpl.rcParams[key] == mpl.rcParamsDefault[key]
            for key in mpl.rcParamsDefault
            if key not in {"backend", "backend_fallback"}
        )
        if (packet.get("selected_model") != ALGO08V2
                or mpl.__version__ != _QUALIFIED_MATPLOTLIB or not default_style):
            raise UnsupportedLayout("Matplotlib version, style or publication model differs")
        with (patch.object(plots, "Figure", _LayoutFigure),
              patch.object(orbit_plot, "Figure", _OrbitFigure)):
            return render_shared_pixels(packet, **kwargs)
    except UnsupportedLayout:
        if require_trial:
            raise
    return render_shared_pixels(packet, **kwargs)
