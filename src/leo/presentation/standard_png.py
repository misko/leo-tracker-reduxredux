"""Deterministic, bounded PNG rendering for Standard presentation views."""

from __future__ import annotations

import struct
import zlib

from leo.presentation.standard_pipeline import StandardPlotViewV2, StandardViewKindV2

_WIDTH = 1200
_HEIGHT = 360
_MARGIN_X = 24
_MARGIN_Y = 20
_LANE_COLORS = (
    (97, 214, 220),
    (246, 200, 95),
    (103, 197, 135),
    (238, 125, 137),
)


def render_standard_plot_png(view: StandardPlotViewV2) -> bytes:
    """Render one verified bounded presentation view without reading scientific inputs."""

    pixels = bytearray((7, 18, 22) * (_WIDTH * _HEIGHT))
    _draw_grid(pixels)
    if view.view_kind == StandardViewKindV2.WATERFALL:
        _draw_waterfall(pixels, view)
    elif view.view_kind == StandardViewKindV2.CFO_TRAJECTORY:
        _draw_cfo(pixels, view)
    else:
        _draw_metric(pixels, view)
    return _png_bytes(pixels)


def _draw_grid(pixels: bytearray) -> None:
    for index in range(1, 6):
        x = _MARGIN_X + index * (_WIDTH - 2 * _MARGIN_X) // 6
        _line(pixels, x, _MARGIN_Y, x, _HEIGHT - _MARGIN_Y, (25, 48, 52))
    for index in range(1, 4):
        y = _MARGIN_Y + index * (_HEIGHT - 2 * _MARGIN_Y) // 4
        _line(pixels, _MARGIN_X, y, _WIDTH - _MARGIN_X, y, (25, 48, 52))
    _line(
        pixels,
        _MARGIN_X,
        _HEIGHT - _MARGIN_Y,
        _WIDTH - _MARGIN_X,
        _HEIGHT - _MARGIN_Y,
        (90, 112, 115),
    )
    _line(
        pixels,
        _MARGIN_X,
        _MARGIN_Y,
        _MARGIN_X,
        _HEIGHT - _MARGIN_Y,
        (90, 112, 115),
    )


def _draw_metric(pixels: bytearray, view: StandardPlotViewV2) -> None:
    for series in view.series:
        lane = view.receiver_path_ids.index(series.receiver_path_id)
        points = [
            (
                _scale_x(
                    point.time_s, view.time_domain.elapsed_start_s, view.time_domain.elapsed_end_s
                ),
                _scale_y(
                    point.value,
                    view.vertical_axis.full_source_min,
                    view.vertical_axis.full_source_max,
                ),
            )
            for point in series.points
        ]
        _polyline(pixels, points, _LANE_COLORS[lane % len(_LANE_COLORS)], width=2)


def _draw_waterfall(pixels: bytearray, view: StandardPlotViewV2) -> None:
    power_min = view.color_axis.full_source_min if view.color_axis is not None else 0.0
    power_max = view.color_axis.full_source_max if view.color_axis is not None else 1.0
    for cell in view.waterfall_cells:
        x = _scale_x(
            cell.frequency_hz,
            view.horizontal_axis.full_source_min,
            view.horizontal_axis.full_source_max,
        )
        # Waterfall convention requested by the operator: elapsed time increases downward.
        y = _scale_y_down(
            cell.time_s,
            view.time_domain.elapsed_start_s,
            view.time_domain.elapsed_end_s,
        )
        ratio = _ratio(cell.power_db, power_min, power_max)
        color = _heat_color(ratio)
        _disc(pixels, x, y, 3, color)


def _draw_cfo(pixels: bytearray, view: StandardPlotViewV2) -> None:
    for point in view.cfo_observations:
        lane = view.receiver_path_ids.index(point.receiver_path_id)
        _disc(
            pixels,
            _scale_x(
                point.time_s,
                view.time_domain.elapsed_start_s,
                view.time_domain.elapsed_end_s,
            ),
            _scale_y(
                point.baseband_cfo_hz,
                view.vertical_axis.full_source_min,
                view.vertical_axis.full_source_max,
            ),
            2,
            _LANE_COLORS[lane % len(_LANE_COLORS)],
        )
    degree_colors = {1: (246, 200, 95), 2: (103, 197, 135), 3: (238, 125, 137)}
    for curve in view.trajectory_curves:
        points = [
            (
                _scale_x(
                    point.time_s,
                    view.time_domain.elapsed_start_s,
                    view.time_domain.elapsed_end_s,
                ),
                _scale_y(
                    point.value,
                    view.vertical_axis.full_source_min,
                    view.vertical_axis.full_source_max,
                ),
            )
            for point in curve.points
        ]
        _polyline(pixels, points, degree_colors[curve.degree], width=3)


def _scale_x(value: float, minimum: float, maximum: float) -> int:
    return _MARGIN_X + round(_ratio(value, minimum, maximum) * (_WIDTH - 2 * _MARGIN_X))


def _scale_y(value: float, minimum: float, maximum: float) -> int:
    return _HEIGHT - _MARGIN_Y - round(_ratio(value, minimum, maximum) * (_HEIGHT - 2 * _MARGIN_Y))


def _scale_y_down(value: float, minimum: float, maximum: float) -> int:
    return _MARGIN_Y + round(_ratio(value, minimum, maximum) * (_HEIGHT - 2 * _MARGIN_Y))


def _ratio(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.5
    return min(1.0, max(0.0, (value - minimum) / (maximum - minimum)))


def _heat_color(value: float) -> tuple[int, int, int]:
    # Dark blue -> cyan -> yellow, with no dependency on a mutable plotting stack.
    if value < 0.5:
        amount = value * 2.0
        return (round(10 + amount * 40), round(30 + amount * 190), round(80 + amount * 155))
    amount = (value - 0.5) * 2.0
    return (round(50 + amount * 205), round(220 + amount * 30), round(235 - amount * 175))


def _polyline(
    pixels: bytearray,
    points: list[tuple[int, int]],
    color: tuple[int, int, int],
    *,
    width: int,
) -> None:
    for start, end in zip(points, points[1:], strict=False):
        _line(pixels, *start, *end, color, width=width)


def _line(
    pixels: bytearray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    *,
    width: int = 1,
) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        _disc(pixels, x0, y0, max(0, width - 1), color)
        if x0 == x1 and y0 == y1:
            return
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def _disc(
    pixels: bytearray,
    center_x: int,
    center_y: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    for y in range(center_y - radius, center_y + radius + 1):
        for x in range(center_x - radius, center_x + radius + 1):
            if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius**2:
                _pixel(pixels, x, y, color)


def _pixel(
    pixels: bytearray,
    x: int,
    y: int,
    color: tuple[int, int, int],
) -> None:
    if not (0 <= x < _WIDTH and 0 <= y < _HEIGHT):
        return
    offset = (y * _WIDTH + x) * 3
    pixels[offset : offset + 3] = bytes(color)


def _png_bytes(pixels: bytearray) -> bytes:
    rows = b"".join(
        b"\x00" + pixels[row * _WIDTH * 3 : (row + 1) * _WIDTH * 3] for row in range(_HEIGHT)
    )
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", _WIDTH, _HEIGHT, 8, 2, 0, 0, 0)
    return (
        signature
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows, 9))
        + _chunk(b"IEND", b"")
    )


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))
