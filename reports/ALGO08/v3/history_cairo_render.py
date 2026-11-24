"""Use the guarded six-sheet renderer at the standard publication boundary."""

from contextlib import contextmanager
from unittest.mock import patch


SOURCES = ("history_cairo_render.py", "direct_orbit_entry.py", "direct_orbit_figures.py",
           "direct_residual_entry.py", "direct_residual_figures.py", "one_pass_web_png.py")


@contextmanager
def binding(scan, audit):
    original = scan.render

    def render(packet, **options):
        from direct_orbit_entry import native_orbits
        from direct_residual_entry import render as residual

        if audit:
            raise ValueError("Expected one complete standard figure request")
        orbit = {}
        with native_orbits(original, orbit):
            images, layout = residual(original, packet, explicit_layout=True, **options)
        audit.update(orbit | layout)
        return images

    with patch.object(scan, "render", render):
        yield
