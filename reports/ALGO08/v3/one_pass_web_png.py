"""Lay out the existing web figure artists before their single Agg draw."""

from collections import Counter
from contextlib import contextmanager
from unittest.mock import patch


class UnsupportedWebLayout(ValueError):
    """A figure does not fit the fixed publication templates."""


@contextmanager
def one_pass_layout(*, enabled):
    from tools.pipeline_eval.variants.experimental import raster_layout

    counts = Counter()
    if not enabled:
        yield counts
        return

    class Figure(raster_layout._LayoutFigure):
        def __init__(self, *args, **options):
            if options.get("layout") != "constrained":
                raise UnsupportedWebLayout("Unknown standard figure layout")
            super().__init__(*args, **dict(options, layout="none"))
            self.template = tuple(self.get_size_inches())
            self.placed = False

        def draw(self, renderer):
            if not self.placed:
                if self.template == (15, 11) and len(self.axes) == 8:
                    self.subplots_adjust(left=.07, right=.98, bottom=.065, top=.90,
                                         hspace=.63, wspace=.21)
                    counts["residual_figures"] += 1
                elif self.template == (16, 6) and len(self.axes) == 1:
                    labels = self.axes[0].get_xticklabels()
                    longest = max((t.get_window_extent(renderer).height for t in labels),
                                  default=0) / self.dpi
                    bottom = (.33 + longest) / self.template[1]
                    if bottom > .62:
                        raise UnsupportedWebLayout("Track label needs more vertical space")
                    self.subplots_adjust(left=.052, right=.985, bottom=max(.13, bottom), top=.87)
                    counts["track_figures"] += 1
                elif self.template == (14, 8) and len(self.axes) in (2, 3):
                    self.subplots_adjust(left=.065, right=.967, bottom=.14, top=.83, wspace=.32)
                    if len(self.axes) == 3:
                        grid, _, colorbar = self.axes
                        bounds, bar = grid.get_position(), colorbar.get_position()
                        colorbar.set_axes_locator(None)
                        colorbar.set_position((bar.x0, bounds.y0, bar.width, bounds.height))
                    counts["position_figures"] += 1
                else:
                    raise UnsupportedWebLayout("Unknown standard figure dimensions")
                self.placed = True
            super().draw(renderer)

    class OrbitFigure(raster_layout._OrbitFigure):
        def tight_layout(self, *, rect=None, pad=1.08, **options):
            if rect is None or rect[0] != 0 or rect[2] != 1 or options:
                raise UnsupportedWebLayout("Unknown orbit figure layout bounds")
            height = self.get_size_inches()[1]
            # The original legend is anchored to the page, not the shared x-axis.
            footer = rect[1] + .62 / height + max(0., .025 - .50 / height)
            self.subplots_adjust(left=.07, right=.97, bottom=footer,
                                 top=rect[3] - .37 / height, hspace=.37)
            counts["orbit_figures"] += 1

    with (
        patch.object(raster_layout, "_LayoutFigure", Figure),
        patch.object(raster_layout, "_OrbitFigure", OrbitFigure),
    ):
        yield counts


def render(renderer, packet, *, enabled, **options):
    """Use the installed layout for an unsupported figure without changing its content."""
    try:
        with one_pass_layout(enabled=enabled) as stats:
            return renderer(packet, **options), dict(stats)
    except UnsupportedWebLayout as error:
        if not enabled:
            raise
        return renderer(packet, **options), {"layout_fallback": str(error)}
