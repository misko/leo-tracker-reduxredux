"""Skip the disabled artist walk after ordinary Agg constrained layout."""

from collections import Counter
from contextlib import contextmanager
from functools import wraps
from io import BytesIO
from time import process_time_ns
from unittest.mock import patch


@contextmanager
def layout_only_prepass(*, enabled):
    import matplotlib as mpl
    from matplotlib.backends.backend_agg import FigureCanvasAgg, RendererAgg
    from matplotlib.figure import Figure
    from matplotlib.layout_engine import ConstrainedLayoutEngine

    stats = Counter()
    if mpl.__version__ != "3.11.1":
        yield stats
        return
    original_print, original_disabled, original_draw = FigureCanvasAgg.print_figure, RendererAgg._draw_disabled, Figure.draw
    saving = inactive = None

    @wraps(original_print)
    def print_figure(canvas, filename, *args, **options):
        nonlocal saving
        previous = saving
        if (type(canvas) is FigureCanvasAgg and type(filename) is BytesIO and not args
                and options.get("format") == "png" and options.get("backend") is None
                and options.get("bbox_inches") is None and mpl.rcParams["savefig.bbox"] is None
                and options.get("bbox_extra_artists") is None):
            saving = canvas.figure
        else:
            saving = None
        try:
            return original_print(canvas, filename, *args, **options)
        finally:
            saving = previous

    @contextmanager
    def disabled(renderer):
        nonlocal inactive
        previous, inactive = inactive, renderer
        try:
            with original_disabled(renderer):
                yield
        finally:
            inactive = previous

    @wraps(original_draw)
    def draw(figure, renderer):
        engine = figure.get_layout_engine()
        if (figure is not saving or renderer is not inactive or type(engine) is not ConstrainedLayoutEngine
                or not figure.get_visible() or not figure.axes or figure.subfigs
                or figure.canvas.callbacks.callbacks.get("draw_event")):
            prefix = "final_draw" if figure is saving else "other_draw"
            start = process_time_ns()
            result = original_draw(figure, renderer)
            stats[prefix + "_cpu_ns"] += process_time_ns()-start
            stats[prefix + "s"] += 1
            return result
        stats["prepasses"] += 1
        start = process_time_ns()
        if enabled:
            with figure._render_lock:
                # Matplotlib's draw normally applies aspect before running layout.
                figure._get_draw_artists(renderer)
                engine.execute(figure)
            stats["layout_only"] += 1
        else:
            original_draw(figure, renderer)
        stats["prepass_cpu_ns"] += process_time_ns()-start

    with (patch.object(FigureCanvasAgg, "print_figure", print_figure),
          patch.object(RendererAgg, "_draw_disabled", disabled),
          patch.object(Figure, "draw", draw)):
        yield stats
