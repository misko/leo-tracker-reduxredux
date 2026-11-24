"""Use the guarded six-sheet renderer at the standard publication boundary."""

from contextlib import contextmanager
from unittest.mock import patch


SOURCES = ("history_cairo_render.py", "direct_orbit_entry.py", "direct_orbit_figures.py",
           "direct_residual_entry.py", "direct_residual_figures.py", "one_pass_web_png.py")
RESIDUAL_SOURCES = ("history_cairo_render.py", "direct_residual_entry.py", "direct_residual_figures.py", "one_pass_web_png.py")


@contextmanager
def ordinary_orbits(audit):
    """Observe the original orbit plotter without changing its figure factory."""
    from leo.contracts.fast_scan_orbits import PLOT_NAMES
    from tools.pipeline_eval.variants.experimental import raster_layout
    from empty_bootstrap import clock, now

    original = raster_layout.render_shared
    audit["ordinary_orbit_draws"] = []

    def render(*args, **options):
        started = now()
        images = original(*args, **options)
        timing = clock(started)
        if tuple(images) != tuple(PLOT_NAMES):
            raise ValueError("The original orbit renderer did not return all four sheets")
        audit["ordinary_orbit_draws"].append(timing | {"figures": len(images)})
        return images

    with patch.object(raster_layout, "render_shared", render):
        yield


@contextmanager
def binding(scan, audit, *, orbit_sheets=True):
    original = scan.render

    def render(packet, **options):
        from direct_residual_entry import render as residual

        if audit:
            raise ValueError("Expected one complete standard figure request")
        orbit = {}
        if orbit_sheets:
            from direct_orbit_entry import native_orbits

            with native_orbits(original, orbit):
                images, layout = residual(original, packet, explicit_layout=True, **options)
        else:
            with ordinary_orbits(orbit):
                images, layout = residual(original, packet, explicit_layout=True, explicit_orbits=False, **options)
        audit.update(orbit | layout)
        return images

    with patch.object(scan, "render", render):
        yield
