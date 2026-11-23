"""Rebuild the standard shared orbit scenes and draw them directly with Cairo."""

from contextlib import contextmanager
import ctypes as ct
import math
import sys

import numpy as np

from direct_residual_figures import Canvas, TextExtent, cairo_library, ticks


DPI, WIDTH = 150, 2400
GRAY = (.4588235294117647,) * 3
VIEWS = ("all", "unassociated")
XLABEL = "Receive time since capture start (s)"
YLABEL = "Wrapped CFO (kHz)"


def scene(lanes, *, title, alias_period_hz, subtitle=""):
    from matplotlib import colormaps
    from leo.presentation.orbit_plot import _curve_samples, _frequency, _validate

    if not math.isfinite(alias_period_hz) or alias_period_hz <= 0:
        raise ValueError("Expected the standard wrapped frequency frame")
    plots = {}
    for low, high in ((1, 4), (5, 8)):
        selected = tuple(lane for lane in lanes if low <= int(lane.channel[2:]) <= high)
        _validate(selected)
        satellites = sorted({curve.satellite_id for lane in selected for curve in lane.curves})
        palette = colormaps["turbo"]
        colors = {sat: tuple(palette((i+.5) / len(satellites)))[:3] for i, sat in enumerate(satellites)}
        legend = [("Unassociated", GRAY), *colors.items()]
        rows = []
        for lane in selected:
            peaks = {None: []}
            for peak in lane.peaks:
                peaks.setdefault(peak.satellite_id, []).append((peak.time_s, peak.frequency_hz))
            for satellite, values in peaks.items():
                pairs = np.array(values, dtype=np.float64).reshape(-1, 2)
                pairs[:, 1] = _frequency(pairs[:, 1], alias_period_hz) / 1000
                peaks[satellite] = pairs
            curves = [(colors[curve.satellite_id], np.column_stack(_curve_samples(curve, alias_period_hz)))
                      for curve in lane.curves]
            count, loose = len(lane.peaks), len(peaks[None])
            name = f"{lane.receiver} · {lane.channel}"
            rows.append(dict(
                titles=(f"{name} · all {count:,} · {count-loose:,} associated + {loose:,} unassociated",
                        f"{name} · unassociated only: {loose:,}/{count:,}"),
                loose=peaks[None], curves=curves,
                associated=[(colors[s], peaks[s]) for s in sorted(s for s in peaks if s is not None)],
            ))
        count = sum(len(lane.peaks) for lane in selected)
        loose = sum(len(row["loose"]) for row in rows)
        plots[f"ch{low}-{high}"] = dict(
            headings=(f"{title} · CH{low}–{high}",
                      f"{count-loose:,}/{count:,} associated top-one passing GLRT windows · {loose:,} unassociated")
                     + ((subtitle,) if subtitle else ()),
            footers=("Selected satellite orbit predictions + all supplied GLRT observations."
                     " Colors denote satellite IDs; no alias copies or refitting.",
                     "Selected satellite orbit predictions + unassociated GLRT only."
                     " Colors denote satellite IDs; no alias copies or refitting."),
            rows=rows, legend=legend, legend_rows=max(1, math.ceil(len(legend)/6)),
            xlim=(0., 300.), ylim=(-alias_period_hz/2000, alias_period_hz/2000),
        )
    return plots


class OrbitCanvas(Canvas):
    def text(self, x, y, body, points, **options):
        return super().text(x, y, body, points * DPI / 125, **options)

    def alpha(self, color, alpha):
        self.c.cairo_set_source_rgba(self.ctx, *color, alpha)

    def text_width(self, body, points):
        extent = TextExtent()
        self.c.cairo_set_font_size(self.ctx, points * DPI / 72)
        self.c.cairo_text_extents(self.ctx, body.encode("utf-8"), ct.byref(extent))
        return extent.width


def library():
    c = cairo_library()
    c.cairo_set_source_rgba.argtypes = [ct.c_void_p] + [ct.c_double] * 4
    c.cairo_set_source_rgba.restype = None
    c.cairo_surface_mark_dirty.argtypes = [ct.c_void_p]
    c.cairo_surface_mark_dirty.restype = None
    return c


@contextmanager
def surface(c, height):
    if sys.byteorder != "little":
        raise ValueError("The reviewed Cairo transfer requires little-endian pixels")
    s = c.cairo_image_surface_create(1, WIDTH, height)
    ctx = c.cairo_create(s)
    try:
        if c.cairo_status(ctx) or c.cairo_surface_status(s):
            raise ValueError("Could not allocate an original-sized Cairo orbit sheet")
        stride = c.cairo_image_surface_get_stride(s)
        pixels = np.ctypeslib.as_array(c.cairo_image_surface_get_data(s), (height*stride,))
        pixels = pixels.reshape(height, stride)[:, :WIDTH*4].reshape(height, WIDTH, 4)
        yield OrbitCanvas(c, ctx), s, pixels
    finally:
        c.cairo_destroy(ctx)
        c.cairo_surface_destroy(s)


def transforms(plot, box):
    x, y, w, h = box
    low, high = plot["ylim"]
    return lambda value: x + w*value/300., lambda value: y + h*(high-value)/(high-low)


def geometry(plot):
    n = len(plot["rows"])
    height = int((2.3*n + 1.5 + .25*plot["legend_rows"])*DPI)
    footer = (.5 + .25*plot["legend_rows"] + .62)*DPI + max(0., .025*height-.50*DPI)
    top = 1.37*DPI
    axis_height = (height-footer-top)/(n + (n-1)*.37)
    return height, [(WIDTH*.07, top+i*axis_height*1.37, WIDTH*.90, axis_height) for i in range(n)]


def lane_ticks(plot, box):
    return ticks(plot["xlim"], 9), ticks(plot["ylim"], max(2, int(box[3]*72/(DPI*20))))


def scatter(canvas, points, color, alpha, marker, px, py):
    c, ctx = canvas.c, canvas.ctx
    canvas.alpha(color, alpha)
    for time, frequency in points:
        c.cairo_new_sub_path(ctx)
        c.cairo_arc(ctx, px(time), py(frequency), marker, 0., 2*math.pi)
        if alpha != 1:
            c.cairo_fill(ctx)
    if alpha == 1:
        c.cairo_fill(ctx)


def curve(canvas, points, color, px, py):
    c, ctx = canvas.c, canvas.ctx
    canvas.alpha(color, .75)
    c.cairo_set_line_width(ctx, DPI/72)
    open_path = False
    for time, frequency in points:
        if not (math.isfinite(time) and math.isfinite(frequency)):
            open_path = False
        elif open_path:
            c.cairo_line_to(ctx, px(time), py(frequency))
        else:
            c.cairo_move_to(ctx, px(time), py(frequency))
            open_path = True
    c.cairo_stroke(ctx)


def base_lane(canvas, plot, row, box, *, bottom):
    c, ctx = canvas.c, canvas.ctx
    x, y, w, h = box
    px, py = transforms(plot, box)
    xt, yt = lane_ticks(plot, box)
    canvas.ink(.86, .86, .86)
    for value, _ in xt:
        canvas.line(px(value), y, px(value), y+h, 1.)
    for value, _ in yt:
        canvas.line(x, py(value), x+w, py(value), 1.)

    c.cairo_save(ctx)
    c.cairo_rectangle(ctx, x, y, w, h)
    c.cairo_clip(ctx)
    scatter(canvas, row["loose"], GRAY, .7, math.sqrt(11)*DPI/144, px, py)
    for color, points in row["curves"]:
        curve(canvas, points, color, px, py)
    c.cairo_restore(ctx)

    canvas.ink(0., 0., 0.)
    c.cairo_set_line_width(ctx, .8*DPI/72)
    c.cairo_rectangle(ctx, x, y, w, h)
    c.cairo_stroke(ctx)
    for value, label in yt:
        canvas.line(x-7, py(value), x, py(value), 1.6)
        canvas.text(x-14, py(value)+7, label, 10, anchor=1)
    canvas.text(x-78, y+h/2, YLABEL, 10, rotated=True)
    for value, label in xt:
        canvas.line(px(value), y+h, px(value), y+h+7, 1.6)
        if bottom:
            canvas.text(px(value), y+h+28, label, 10)
    if bottom:
        canvas.text(x+w/2, y+h+55, XLABEL, 10)
    return xt, yt


def legend_columns(entries, text_width):
    groups = np.array_split(np.arange(len(entries)), min(len(entries), 6))
    widths = [max(text_width(entries[i][0], 8) for i in group) + 72 for group in groups]
    span = sum(widths)
    if span > WIDTH * .9:
        raise ValueError("The orbit legend exceeds the reviewed footer width")
    return zip((WIDTH - span)/2 + np.r_[0., np.cumsum(widths[:-1])], groups, strict=True)


def legend(canvas, entries, height):
    for x, group in legend_columns(entries, canvas.text_width):
        for row, index in enumerate(group[::-1]):
            name, color = entries[index]
            y = height*.975 - 24 - row*22
            canvas.ink(*color)
            if index:
                canvas.line(x, y-5, x+34, y-5, DPI/72)
            scatter(canvas, [(x+17, y-5)], color, 1, 4, lambda z: z, lambda z: z)
            canvas.ink(0., 0., 0.)
            canvas.text(x+46, y, name, 8, anchor=0)


def raster(plot, c, save):
    rows = plot["rows"]
    height, boxes = geometry(plot)
    with surface(c, height) as (canvas, surface_id, pixels):
        ctx = canvas.ctx
        canvas.ink(1., 1., 1.)
        c.cairo_paint(ctx)
        canvas.ink(0., 0., 0.)
        for i, text in enumerate(plot["headings"]):
            canvas.text(WIDTH/2, .01*height+30+i*33, text, 15)
        tick_sets = [base_lane(canvas, plot, row, box, bottom=i == len(rows)-1)
                     for i, (row, box) in enumerate(zip(rows, boxes, strict=True))]
        legend(canvas, plot["legend"], height)
        c.cairo_surface_flush(surface_id)
        base = pixels.copy()
        outputs = {}
        for index, name in enumerate(VIEWS):
            if index:
                np.copyto(pixels, base)
                c.cairo_surface_mark_dirty(surface_id)
            for row, box in zip(rows, boxes, strict=True):
                x, y, w, _ = box
                canvas.ink(0., 0., 0.)
                canvas.text(x+w/2, y-12, row["titles"][index], 10)
                if index == 0:
                    c.cairo_save(ctx)
                    c.cairo_rectangle(ctx, *box)
                    c.cairo_clip(ctx)
                    px, py = transforms(plot, box)
                    for color, points in row["associated"]:
                        scatter(canvas, points, color, 1., math.sqrt(12)*DPI/144, px, py)
                    c.cairo_restore(ctx)
            canvas.ink(0., 0., 0.)
            canvas.text(WIDTH/2, height*.992, plot["footers"][index], 8)
            if (c.cairo_status(ctx) or c.cairo_surface_status(surface_id)
                    or any(x < 0 or y < 0 or r > WIDTH or b > height for x, y, r, b in canvas.text_boxes)):
                raise ValueError("The native orbit sheet failed or clipped a label")
            c.cairo_surface_flush(surface_id)
            rgba = np.empty_like(pixels)
            rgba[..., :3] = pixels[..., 2::-1]
            rgba[..., 3] = 255
            outputs[name] = save(rgba)
    return outputs, tick_sets
