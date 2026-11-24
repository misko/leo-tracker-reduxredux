"""Compact, trial-only display data witness for the actual stock and Cairo draws."""

from contextlib import contextmanager
from hashlib import sha256
from time import process_time_ns
from unittest.mock import patch


def coordinates(data):
    import numpy as np

    values = np.asarray(data, dtype="<f8")
    return dict(shape=list(values.shape), sha256=sha256(values.tobytes()).hexdigest())


def limits(axis):
    return dict(title=axis.get_title(), xlabel=axis.get_xlabel(), ylabel=axis.get_ylabel(),
                xlim=axis.get_xlim(), ylim=axis.get_ylim())


def lines(axis):
    from matplotlib.colors import to_rgba

    return [(to_rgba(artist.get_color())[:3], coordinates(artist.get_xydata())) for artist in axis.lines]


def collections(axis):
    return [(tuple(artist.get_facecolors()[0, :3]), coordinates(artist.get_offsets()))
            for artist in axis.collections if len(artist.get_facecolors())]


def visible_ticks(axis):
    return [[(round(float(tick.get_loc()), 10), label.get_text()) for tick in direction.get_major_ticks()
             for label in (tick.label1, tick.label2) if label.get_visible() and lo <= tick.get_loc() <= hi]
            for direction, (lo, hi) in ((axis.xaxis, axis.get_xlim()), (axis.yaxis, axis.get_ylim()))]


def direct_ticks(ticks):
    return [[(round(float(value), 10), label) for value, label in axis] for axis in ticks]


def stock_special(figure):
    return dict(heading=figure._suptitle.get_text() if figure._suptitle else None,
                axes=[limits(ax) | {"lines": lines(ax), "offsets": collections(ax),
                                    "bars": [(bar.get_x(), bar.get_y(), bar.get_width(), bar.get_height())
                                             for bar in ax.patches if hasattr(bar, "get_height")]}
                      for ax in figure.axes], ticks=[visible_ticks(ax) for ax in figure.axes])


def stock_orbit(figure):
    return dict(heading=figure._suptitle.get_text(), footer=figure.texts[-1].get_text(),
                legend=[text.get_text() for text in figure.legends[0].get_texts()],
                axes=[limits(ax) | {"lines": lines(ax), "offsets": collections(ax)} for ax in figure.axes],
                ticks=[visible_ticks(ax) for ax in figure.axes])


def native_orbit(plot, ticks):
    from direct_orbit_figures import GRAY, XLABEL, YLABEL

    axes = []
    for i, row in enumerate(plot["rows"]):
        axes.append(dict(title=row["titles"][0], xlabel=XLABEL if i == len(plot["rows"])-1 else "", ylabel=YLABEL,
                         xlim=plot["xlim"], ylim=plot["ylim"],
                         lines=[(color, coordinates(values)) for color, values in row["curves"]],
                         offsets=[(color, coordinates(values)) for color, values in [(GRAY, row["loose"]), *row["associated"]]]))
    labels = [direct_ticks(axis) for axis in ticks]
    for horizontal, _ in labels[:-1]:
        horizontal.clear()
    return dict(heading="\n".join(plot["headings"]), footer=plot["footers"][0],
                legend=[name for name, _ in plot["legend"]], axes=axes, ticks=labels)


def stock_residual(figure):
    return dict(heading=figure._suptitle.get_text(), axes=[limits(ax) | {"zero": list(ax.lines[0].get_ydata()),
                "offsets": collections(ax)} for ax in figure.axes], ticks=[visible_ticks(ax) for ax in figure.axes])


def native_residual(chart, ticks):
    return dict(heading="\n".join(chart["heading"]), axes=[{k: v for k, v in ax.items() if k != "series"} |
                {"zero": [0, 0], "offsets": [(tuple(b/255 for b in bytes.fromhex(color)), coordinates(values))
                                              for color, values in ax["series"]]} for ax in chart["axes"]],
                ticks=[direct_ticks(axis) for axis in ticks])


@contextmanager
def capture(audit, color):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import direct_orbit_figures as orbit
    import direct_residual_figures as residual

    draw, draw_orbit, draw_residual = FigureCanvasAgg.draw, orbit.raster, residual.raster
    counted = set()
    audit.update(orbit=[], residual=[], standard={}, cpu_ns=0)

    def record(produce, *args):
        started = process_time_ns()
        try:
            return produce(*args)
        finally:
            audit["cpu_ns"] += process_time_ns()-started

    def actual(canvas, *args, **options):
        result = draw(canvas, *args, **options)
        fig = canvas.figure
        if fig not in counted:
            counted.add(fig)
            width, height = fig.get_size_inches()
            if (width, height) in ((14, 8), (16, 6)):
                named = "position" if width == 14 else "track-rms"
                audit["standard"][named] = record(stock_special, fig)
            elif not color and (width, height) == (15, 11):
                audit["residual"].append(record(stock_residual, fig))
            elif not color and width == 16 and len(fig.axes) == 8:
                audit["orbit"].append(record(stock_orbit, fig))
        return result

    def actual_orbit(plot, lib, save):
        images, ticks = draw_orbit(plot, lib, save)
        audit["orbit"].append(record(native_orbit, plot, ticks))
        return images, ticks

    def actual_residual(chart, lib):
        image, ticks = draw_residual(chart, lib)
        audit["residual"].append(record(native_residual, chart, ticks))
        return image, ticks

    with (patch.object(FigureCanvasAgg, "draw", actual), patch.object(orbit, "raster", actual_orbit),
          patch.object(residual, "raster", actual_residual)):
        yield
