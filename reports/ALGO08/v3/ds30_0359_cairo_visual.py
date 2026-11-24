"""Replay the captured orbit lanes and evaluate the frozen visual gates."""

from functools import partial
from hashlib import sha256
from io import BytesIO
import pickle
from unittest.mock import patch


def scene_view(plot, index):
    return dict(plot, footers=(plot["footers"][index],), rows=[
        dict(row, titles=(row["titles"][index],), associated=row["associated"] if index == 0 else [])
        for row in plot["rows"]])


def artist_check(stock, direct):
    return {key: stock[key] == direct[key] for key in ("heading", "footer", "legend", "axes", "ticks")}


def products(capture):
    import empty_bootstrap as boot

    _, specification, _, _, _ = boot.load_runtime()
    from direct_orbit_entry import native_orbits
    import direct_orbit_figures as orbit
    from history_cairo_artists import native_orbit, stock_orbit
    from leo.presentation import orbit_plot
    from matplotlib import image
    from pathlib import Path
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout, shared_orbit_figures as shared

    # The captured file is authored by the candidate and hash checked against
    # its sealed prediction before loading. No other pickle is accepted.
    with capture.open("rb") as stream:
        lanes, options = pickle.load(stream)
    libs = {}
    for key in ("png_filter", "png_deflate"):
        pin = specification[key]
        path = Path(pin["library"])
        boot.checked(path, pin["sha256"])
        libs[key] = path
    encoder = lossless_png.LosslessPng(libs["png_filter"], deflate_library=libs["png_deflate"])
    installed = partial(lossless_png.render_lossless_png, encoder=encoder)
    installed_figure, draw = shared.make_orbit_plot, orbit.raster
    figure = None
    stock_artists, cairo_artists, metrics = [], [], {}

    def observe(*args, **kwargs):
        nonlocal figure
        figure = installed_figure(*args, **kwargs)
        return figure

    save = encoder.wrap(shared.imsave)

    def stock_save(*args, **kwargs):
        values = stock_orbit(figure)
        for row, axis in zip(values["axes"], figure.axes, strict=True):
            visible = (item.get_visible() for item in axis.collections if len(item.get_facecolors()))
            row["offsets"] = [item for item, seen in zip(row["offsets"], visible, strict=True) if seen]
        stock_artists.append(values)
        return save(*args, **kwargs)

    with (patch.object(orbit_plot, "Figure", raster_layout._OrbitFigure),
          patch.object(shared, "make_orbit_plot", observe), patch.object(shared, "imsave", stock_save)):
        ordinary = shared.render_shared(lanes, **options, reuse_pixels=True)

    def native_draw(plot, library, write):
        result, ticks = draw(plot, library, write)
        cairo_artists.extend(native_orbit(scene_view(plot, index), ticks) for index in range(len(orbit.VIEWS)))
        return result, ticks

    with (patch.object(orbit, "raster", native_draw), patch.object(image, "imsave", encoder.wrap(image.imsave)),
          native_orbits(installed, metrics)):
        cairo = raster_layout.render_shared(lanes, **options, reuse_pixels=True)

    gaps = {}
    with orbit.surface(orbit.library(), 20) as (canvas, _, _):
        for band, plot in orbit.scene(lanes, **options).items():
            columns = list(orbit.legend_columns(plot["legend"], canvas.text_width))
            spacing = [b - a - 46 - max(canvas.text_width(plot["legend"][i][0], 8) for i in group)
                       for (a, group), (b, _) in zip(columns, columns[1:])]
            gaps[band] = min(spacing, default=orbit.WIDTH)
    names = [f"{band}-{view}" for band in ("ch1-4", "ch5-8") for view in orbit.VIEWS]
    return ordinary, cairo, dict(zip(names, map(artist_check, stock_artists, cairo_artists), strict=True)), gaps, metrics


def evidence(capture, stores, run, images):
    from history_risk_cairo_0402 import failed_layers
    from named_weak_visual import registered_orbits
    from PIL import Image

    ordinary, cairo, artists, gaps, metrics = products(capture)
    reproduction, raster, dimensions, registration_errors = {}, {}, {}, {}
    for name in ordinary:
        first, second = [store.artifact(run, name, row[name]["sha256"])
                         for store, row in zip(stores, images, strict=True)]
        reproduction[name] = dict(ordinary=ordinary[name] == first, cairo=cairo[name] == second)
        with Image.open(BytesIO(first)) as left, Image.open(BytesIO(second)) as right:
            a, b = left.convert("RGBA"), right.convert("RGBA")
            dimensions[name] = (a.size == b.size and left.mode == right.mode and left.info == right.info)
            for mode, rgba, row in zip(("ordinary", "cairo"), (a, b), images, strict=True):
                reproduction[name][mode + "_decoded"] = sha256(rgba.tobytes()).hexdigest() == row[name]["rgba_sha256"]
            try:
                raster[name] = registered_orbits(a.convert("RGB"), b.convert("RGB"), require_match=False)
            except ValueError as error:
                registration_errors[name] = str(error)
    failed = failed_layers(raster)
    checks = dict(reproduced=len(reproduction) == 4 and all(all(row.values()) for row in reproduction.values()),
                  metadata=all(dimensions.values()), artists=len(artists) == 4 and all(all(row.values()) for row in artists.values()),
                  legend=all(gap >= 20 for gap in gaps.values()), registration=not failed and not registration_errors,
                  rendered=metrics.get("native_orbit_figures") == 4 and "native_orbit_fallback" not in metrics)
    return dict(checks=checks, qualified=all(checks.values()), reproduction=reproduction, artists=artists,
                legend_gap_px=gaps, registration=raster, failed_layers=failed,
                registration_errors=registration_errors, render_replay=metrics)
