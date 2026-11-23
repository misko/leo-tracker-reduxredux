"""Use the reviewed native residual scenes in the explicit-layout renderer."""

from functools import partial
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


PLOT_SHA = "705c59fee15b2d2ab6f97cbaf229918f512c06c61275a6bf739c64df56ebb07f"


class UnsupportedResidualFigures(ValueError):
    pass


class UnusedAxes:
    """The pinned renderer's call site does not need Matplotlib residual axes."""

    def unused(self, *_args, **_options):
        pass

    scatter = axhline = set_ylabel = set_xlabel = set_xlim = set_title = grid = unused


class ResidualFigure:
    def __init__(self, chapter, draw, save):
        self.chapter, self.draw, self.save = chapter, draw, save
        self.ready = False

    def subplots(self, nrows, ncols, *, squeeze):
        import numpy as np

        if (nrows, ncols, squeeze) != (4, 2, False):
            raise UnsupportedResidualFigures("Unreviewed residual axis extent")
        return np.full((nrows, ncols), UnusedAxes(), dtype=object)

    def suptitle(self, title, *, fontsize):
        if tuple(title.split("\n")) != self.chapter["heading"] or fontsize != 11:
            raise UnsupportedResidualFigures("Unreviewed residual figure heading")
        self.ready = True

    def savefig(self, stream, *, format, dpi):
        if not self.ready or (format, dpi) != ("png", 125):
            raise UnsupportedResidualFigures("Unreviewed residual figure save request")
        self.save(stream, self.draw(self.chapter))

    def clear(self):
        self.ready = False


def render(installed, packet, **options):
    from matplotlib import image
    from leo.presentation import fast_standard_analysis as plots
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout
    from direct_residual_figures import cairo_library, raster, scene
    from one_pass_web_png import one_pass_layout, render as incumbent

    def candidate():
        if (type(installed) is not partial or installed.func is not lossless_png.render_lossless_png
                or sha256(Path(plots.__file__).read_bytes()).hexdigest() != PLOT_SHA):
            raise UnsupportedResidualFigures("Unreviewed residual renderer or PNG encoder")
        encoder = installed.keywords["encoder"]
        library = cairo_library()
        chapters = iter(scene(packet, options["title"]).values())
        imsave = image.imsave
        canvas = plots.FigureCanvasAgg
        produced = 0

        def draw(chapter):
            return raster(chapter, library)[0]

        def save(stream, rgba):
            nonlocal produced
            settings = dict(format="png", origin="upper", dpi=125, metadata=None)
            if not encoder._encode(imsave, stream, memoryview(rgba), settings):
                raise UnsupportedResidualFigures("PNG encoder declined the native residual")
            produced += 1

        with one_pass_layout(enabled=True) as counts:
            ordinary = raster_layout._LayoutFigure

            def figure(*args, **kwargs):
                if kwargs == {"figsize": (15, 11), "layout": "constrained"} and not args:
                    chapter = next(chapters, None)
                    if chapter is None:
                        raise UnsupportedResidualFigures("Unexpected extra residual figure")
                    return ResidualFigure(chapter, draw, save)
                return ordinary(*args, **kwargs)

            def drawing(figure, *args, **kwargs):
                if not isinstance(figure, ResidualFigure):
                    return canvas(figure, *args, **kwargs)

            with patch.object(raster_layout, "_LayoutFigure", figure), patch.object(plots, "FigureCanvasAgg", drawing):
                plots_by_name = installed(packet, **options)
        if produced != 2:
            raise UnsupportedResidualFigures("Original layout bypassed the native residual sheets")
        return plots_by_name, dict(counts, native_residual_figures=produced)

    try:
        return candidate()
    except (OSError, ValueError) as error:
        images, counts = incumbent(installed, packet, enabled=True, **options)
        return images, dict(counts, native_residual_fallback=str(error))
