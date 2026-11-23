"""Select the native orbit sheets within the installed explicit renderer."""

from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch


ORBIT_SHA = "e0cef8b115c82ba737f981ec7366f2637de6190434097747538b1a182bcab49c"
SHARED_SHA = "7cb3fb121588341f91f5f6e2167e7c8e9adb1fe10a2b1ca07a2a39039b1fa4af"


@contextmanager
def native_orbits(installed, audit):
    from matplotlib import image
    from leo.presentation import orbit_plot
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout, shared_orbit_figures
    from direct_orbit_figures import DPI, library, raster, scene

    original = raster_layout.render_shared
    imsave = image.imsave

    def render(lanes, *, title, alias_period_hz, subtitle="", reuse_pixels=False):
        start = process_time_ns()
        try:
            if (not reuse_pixels or type(installed) is not partial or installed.func is not lossless_png.render_lossless_png
                    or original is not shared_orbit_figures.render_shared
                    or any(sha256(Path(m.__file__).read_bytes()).hexdigest() != pin for m, pin in (
                        (orbit_plot, ORBIT_SHA), (shared_orbit_figures, SHARED_SHA)))):
                raise ValueError("Unreviewed original orbit source or encode path")
            encoder = installed.keywords["encoder"]
            cortex = library()
            plots = scene(lanes, title=title, alias_period_hz=alias_period_hz, subtitle=subtitle)
            setup_cpu_ns = process_time_ns()-start
            encode_cpu_ns = 0

            def save(rgba):
                nonlocal encode_cpu_ns
                before = process_time_ns()
                stream = BytesIO()
                options = dict(format="png", origin="upper", dpi=DPI)
                if not encoder._encode(imsave, stream, memoryview(rgba), options):
                    raise ValueError("Original PNG encoder declined the native orbit buffer")
                encode_cpu_ns += process_time_ns()-before
                return stream.getvalue()

            products = {}
            for prefix, plot in plots.items():
                images, _ = raster(plot, cortex, save)
                products.update({f"{prefix}-{name}": value for name, value in images.items()})
            total = process_time_ns()-start
            audit.update(native_orbit_figures=len(products), native_orbit_setup_cpu_ns=setup_cpu_ns,
                         native_orbit_encode_cpu_ns=encode_cpu_ns, native_orbit_total_cpu_ns=total)
            return products
        except (OSError, ValueError) as error:
            audit["native_orbit_fallback"] = str(error)
            return original(lanes, title=title, alias_period_hz=alias_period_hz, subtitle=subtitle,
                            reuse_pixels=reuse_pixels)

    with patch.object(raster_layout, "render_shared", render):
        yield
