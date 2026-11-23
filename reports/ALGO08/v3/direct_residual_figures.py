"""Build the standard residual scenes from their selected measurement packet."""

from collections import Counter, defaultdict
import ctypes as ct
import math
import sys

import numpy as np


WIDTH, HEIGHT, DPI = 1875, 1375, 125
PALETTE = (
    "1f77b4", "aec7e8", "ff7f0e", "ffbb78", "2ca02c", "98df8a", "d62728", "ff9896",
    "9467bd", "c5b0d5", "8c564b", "c49c94", "e377c2", "f7b6d2", "7f7f7f", "c7c7c7",
    "bcbd22", "dbdb8d", "17becf", "9edae5",
)


def scene(packet, title):
    from leo.contracts.fast_standard_analysis import standard_label

    model = standard_label(packet.get("selected_model"))
    if model in ("ALGO08", "ALGO08v2"):
        frame = packet["position_grid"]
        lat, lon = frame["region_center"]
        title += f" · {frame['box_width_km']:g} km square at ({lat:.5f}°, {lon:.5f}°)"
    heading = (title, f"{model} selected result · conditional residuals · fitted c")
    rows = packet["rows"]["fitted_c"]
    total = Counter((row["receiver"], row["channel"]) for row in packet["observations"])
    ordered = tuple(sorted({row["norad"] for row in rows}))
    points = defaultdict(list)
    for row in rows:
        points[row["receiver"], row["channel"], row["norad"]].append((row["time_s"], row["residual_hz"]))

    charts = {}
    for first in (1, 5):
        axes = []
        for channel in range(first, first + 4):
            for receiver in (1, 2):
                series = tuple((PALETTE[i % len(PALETTE)], np.asarray(
                    points[receiver, channel, norad], dtype=np.float64).reshape(-1, 2))
                    for i, norad in enumerate(ordered))
                samples = [data[:, 1] for _, data in series if len(data)]
                low, high = (min([0.] + [float(a.min()) for a in samples]),
                             max([0.] + [float(a.max()) for a in samples]))
                if any(not np.isfinite(a).all() for _, a in series) or high - low > 1e6:
                    raise ValueError("Unsupported residual-axis extent")
                if high == low:
                    low, high = -0.05, 0.05
                margin = (high - low) * 0.05
                count = sum(len(a) for _, a in series)
                axes.append(dict(
                    title=f"RX{receiver} CH{channel} · {count}/{total[receiver, channel]} associated",
                    xlabel="Time (s)", ylabel="CFO residual (Hz)", xlim=(0., 300.),
                    ylim=(low-margin, high+margin), series=series,
                ))
        charts[f"ch{first}-{first+3}-residuals"] = dict(heading=heading, axes=axes)
    return charts


def ticks(limits, divisions):
    low, high = limits
    raw = (high-low) / divisions
    decade = 10. ** math.floor(math.log10(raw))
    step = next(decade * value for value in (1, 2, 2.5, 5, 10) if decade * value >= raw)
    places = max(0, -math.floor(math.log10(step)) + (step / decade == 2.5))
    return tuple((i * step, f"{i * step:.{places}f}".replace("-", "−"))
                 for i in range(math.ceil(low/step), math.floor(high/step) + 1))


class TextExtent(ct.Structure):
    _fields_ = [(name, ct.c_double) for name in ("x", "y", "width", "height", "advance", "height_advance")]


def cairo_library():
    c = ct.CDLL("libcairo.so.2")
    handle, integer, real, string = ct.c_void_p, ct.c_int, ct.c_double, ct.c_char_p
    signatures = {
        "image_surface_create": (handle, integer, integer, integer),
        "create": (handle, handle), "destroy": (None, handle), "surface_destroy": (None, handle),
        "surface_flush": (None, handle), "status": (integer, handle), "surface_status": (integer, handle),
        "image_surface_get_stride": (integer, handle),
        "image_surface_get_data": (ct.POINTER(ct.c_uint8), handle),
        "set_source_rgb": (None, handle, real, real, real), "paint": (None, handle),
        "move_to": (None, handle, real, real), "line_to": (None, handle, real, real),
        "set_line_width": (None, handle, real), "stroke": (None, handle),
        "rectangle": (None, handle, real, real, real, real), "clip": (None, handle),
        "save": (None, handle), "restore": (None, handle), "translate": (None, handle, real, real),
        "rotate": (None, handle, real), "new_sub_path": (None, handle),
        "arc": (None, handle, real, real, real, real, real), "fill": (None, handle),
        "select_font_face": (None, handle, string, integer, integer),
        "set_font_size": (None, handle, real),
        "text_extents": (None, handle, string, ct.POINTER(TextExtent)),
        "show_text": (None, handle, string),
    }
    for name, (result, *arguments) in signatures.items():
        operation = getattr(c, "cairo_" + name)
        operation.argtypes, operation.restype = arguments, result
    return c


class Canvas:
    def __init__(self, library, context):
        self.c, self.ctx = library, context
        self.text_boxes = []
        self.c.cairo_select_font_face(self.ctx, b"DejaVu Sans", 0, 0)

    def ink(self, r, g, b):
        self.c.cairo_set_source_rgb(self.ctx, r, g, b)

    def line(self, x0, y0, x1, y1, width):
        c, ctx = self.c, self.ctx
        c.cairo_set_line_width(ctx, width)
        c.cairo_move_to(ctx, x0, y0)
        c.cairo_line_to(ctx, x1, y1)
        c.cairo_stroke(ctx)

    def text(self, x, y, body, points, *, anchor=.5, rotated=False):
        c, ctx = self.c, self.ctx
        glyphs = body.encode("utf-8")
        c.cairo_set_font_size(ctx, points * DPI / 72)
        extent = TextExtent()
        c.cairo_text_extents(ctx, glyphs, ct.byref(extent))
        start = -extent.x - extent.width * anchor
        left, right = start + extent.x, start + extent.x + extent.width
        if rotated:
            self.text_boxes.append((x+extent.y, y-right, x+extent.y+extent.height, y-left))
        else:
            self.text_boxes.append((x+left, y+extent.y, x+right, y+extent.y+extent.height))
        c.cairo_save(ctx)
        c.cairo_translate(ctx, x, y)
        if rotated:
            c.cairo_rotate(ctx, -math.pi / 2)
        c.cairo_move_to(ctx, start, 0)
        c.cairo_show_text(ctx, glyphs)
        c.cairo_restore(ctx)


def draw_axis(canvas, axis, x0, y0, width, height):
    c, ctx = canvas.c, canvas.ctx
    x1, y1 = x0 + width, y0 + height
    low, high = axis["ylim"]
    px = lambda t: x0 + width * t / 300.
    py = lambda f: y1 - height * (f - low) / (high - low)
    x_ticks = ticks(axis["xlim"], 9)
    y_ticks = ticks(axis["ylim"], max(2, int(height * 72 / (DPI * 20))))
    c.cairo_save(ctx)
    c.cairo_rectangle(ctx, x0, y0, width, height)
    c.cairo_clip(ctx)
    marker = (math.sqrt(5) + 1.0) * DPI / 144
    for color, rows in axis["series"]:
        rgb = bytes.fromhex(color)
        canvas.ink(*(channel / 255. for channel in rgb))
        for time, residual in rows:
            c.cairo_new_sub_path(ctx)
            c.cairo_arc(ctx, px(time), py(residual), marker, 0., 2 * math.pi)
        c.cairo_fill(ctx)
    c.cairo_restore(ctx)
    canvas.ink(.80, .80, .80)
    for value, _ in x_ticks:
        canvas.line(px(value), y0, px(value), y1, 1.)
    for value, _ in y_ticks:
        canvas.line(x0, py(value), x1, py(value), 1.)
    canvas.ink(0., 0., 0.)
    canvas.line(x0, py(0.), x1, py(0.), .6 * DPI / 72)
    c.cairo_set_line_width(ctx, .8 * DPI / 72)
    c.cairo_rectangle(ctx, x0, y0, width, height)
    c.cairo_stroke(ctx)
    for value, label in x_ticks:
        canvas.line(px(value), y1, px(value), y1+6, 1.4)
        canvas.text(px(value), y1+24, label, 10)
    for value, label in y_ticks:
        canvas.line(x0-6, py(value), x0, py(value), 1.4)
        canvas.text(x0-12, py(value)+6, label, 10, anchor=1)
    canvas.text((x0+x1)/2, y1+48, axis["xlabel"], 10)
    canvas.text(x0-80, (y0+y1)/2, axis["ylabel"], 10, rotated=True)
    canvas.text((x0+x1)/2, y0-12, axis["title"], 12)
    return x_ticks, y_ticks


def raster(chart, library):
    if sys.byteorder != "little":
        raise ValueError("The native pixel transfer requires little-endian Cairo")
    c = library
    surface = c.cairo_image_surface_create(1, WIDTH, HEIGHT)
    ctx = c.cairo_create(surface)
    try:
        canvas = Canvas(c, ctx)
        canvas.ink(1., 1., 1.)
        c.cairo_paint(ctx)
        canvas.ink(0., 0., 0.)
        for index, heading in enumerate(chart["heading"]):
            canvas.text(WIDTH/2, 43+index*22, heading, 11)
        width = WIDTH * (.98-.07) / (2+.21)
        height = HEIGHT * (.90-.065) / (4+3*.63)
        ticks_by_axis = [
            draw_axis(canvas, axis, WIDTH*.07 + (i%2)*width*1.21, HEIGHT*.10 + (i//2)*height*1.63,
                      width, height) for i, axis in enumerate(chart["axes"])
        ]
        if (c.cairo_status(ctx) or c.cairo_surface_status(surface)
                or any(x0 < 0 or y0 < 0 or x1 > WIDTH or y1 > HEIGHT for x0, y0, x1, y1 in canvas.text_boxes)):
            raise ValueError("Native residual sheet failed or clipped a label")
        c.cairo_surface_flush(surface)
        stride = c.cairo_image_surface_get_stride(surface)
        pixels = np.ctypeslib.as_array(c.cairo_image_surface_get_data(surface), (HEIGHT * stride,))
        rgb = pixels.reshape(HEIGHT, stride)[:, :WIDTH*4].reshape(HEIGHT, WIDTH, 4)
        rgba = np.empty_like(rgb)
        rgba[..., :3] = rgb[..., 2::-1]
        rgba[..., 3] = 255
        return rgba, ticks_by_axis
    finally:
        c.cairo_destroy(ctx)
        c.cairo_surface_destroy(surface)
