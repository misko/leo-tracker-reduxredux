"""Measure remaining exact reuse in the installed Agg orbit sheets."""

import argparse
from collections import Counter, defaultdict
from functools import partial
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import pickle
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SOURCES = {
    "raster_layout.py": "e4614570a3f5f3daf53babd04992a4bb7642ca22958fd3cd8f2efb6cd51227e7",
    "shared_orbit_figures.py": "7cb3fb121588341f91f5f6e2167e7c8e9adb1fe10a2b1ca07a2a39039b1fa4af",
    "orbit_plot.py": "e0cef8b115c82ba737f981ec7366f2637de6190434097747538b1a182bcab49c",
}
CASES = {
    "DS30-0402": (Path("/dev/shm/leo-v3-history-risk-residual-layout-0402-result01"), "live-render.pickle",
                  "c8cdda8f5c6d736df516783b54d7f3d6977d73cef3e3440a7cc37771e5c2668a",
                  "replay.json", "a9b44279fb5fe6cb47202cb16ee63c31616249e1e37ef8d98be34fbf3d5b3bc4"),
    "DS30-0016": (Path("/dev/shm/leo-v3-combined-frame-portable-result02"), "candidate/render-scene.pickle",
                  "e222976de38b98d0147cc6abcf21d90693483b6b3e3154c5c211da0c8ba62361",
                  "render-verification.json", "badb9e557fdf747889115d72a808f94a1f169e4b3b2ada6d2db5fc1b310a43ef"),
}


class RestoreAfterCopy:
    """Permit one redundant restore under the checked shared-orbit call sequence."""

    def __init__(self):
        self.pending = {}

    def copied(self, canvas, bounds, region):
        self.pending.pop(canvas, None)
        if bounds is canvas.figure.bbox:
            self.pending[canvas] = (region, canvas.get_renderer())

    def redundant(self, canvas, region):
        previous = self.pending.pop(canvas, None)
        return previous is not None and previous[0] is region and previous[1] is canvas.get_renderer()


def layout_fields(figure):
    return dict(bbox=tuple(figure.bbox.bounds), dpi=figure.dpi,
                axes=[dict(bbox=tuple(a.bbox.bounds), xlim=a.get_xlim(), ylim=a.get_ylim(),
                           xlabel=a.get_xlabel(), ylabel=a.get_ylabel(), title=a.get_title()) for a in figure.axes],
                heading=figure._suptitle.get_text(), legend=[t.get_text() for t in figure.legends[0].get_texts()])


def orbit_draw(installed, packet, options, *, skip):
    from empty_bootstrap import clock, now
    from matplotlib.backends.backend_agg import FigureCanvasAgg as Canvas
    from tools.pipeline_eval.variants.experimental import raster_layout, shared_orbit_figures as shared

    actual = raster_layout.render_shared
    if actual is not shared.render_shared:
        raise ValueError("Expected the installed shared Agg orbit route")
    spans, figures = defaultdict(list), []
    calls = RestoreAfterCopy()

    def timed(stage, operation):
        def invoke(*args, **kwargs):
            start = now()
            result = operation(*args, **kwargs)
            spans[stage].append(clock(start))
            return result
        return invoke

    def render(lanes, **kwargs):
        if kwargs.get("reuse_pixels") is not True or figures:
            raise ValueError("Expected the normal shared renderer once per publication")
        figure = timed("make_figure", shared.make_orbit_plot)
        original_copy, original_restore = Canvas.copy_from_bbox, Canvas.restore_region
        copy_time = timed("copy", original_copy)
        restore_time = timed("restore", original_restore)

        def construct(*args, **options):
            result = figure(*args, **options)
            figures.append(timed("layout_witness", layout_fields)(result))
            return result

        def copy(canvas, bounds):
            region = copy_time(canvas, bounds)
            if skip:
                calls.copied(canvas, bounds, region)
            return region

        def restore(canvas, region, *args, **kwargs):
            if skip and calls.redundant(canvas, region) and not args and not kwargs:
                spans["redundant"].append(True)
                return None
            return restore_time(canvas, region, *args, **kwargs)

        orbit_factory = raster_layout._OrbitFigure
        with (patch.object(shared, "make_orbit_plot", construct),
              patch.object(orbit_factory, "subplots", timed("subplots", orbit_factory.subplots)),
              patch.object(orbit_factory, "tight_layout", timed("tight_layout", orbit_factory.tight_layout)),
              patch.object(Canvas, "draw", timed("base_draw", Canvas.draw)),
              patch.object(Canvas, "copy_from_bbox", copy), patch.object(Canvas, "restore_region", restore),
              patch.object(shared, "imsave", timed("encode", shared.imsave))):
            return timed("whole_orbit", actual)(lanes, **kwargs)

    with patch.object(raster_layout, "render_shared", render):
        images = installed(packet, require_trial=True, **options)
    expected = dict(make_figure=2, subplots=2, tight_layout=2, base_draw=2, copy=2,
                    restore=2 if skip else 4, redundant=2 if skip else 0, encode=4, whole_orbit=1)
    if len(figures) != 2 or any(len(spans[name]) != count for name, count in expected.items()):
        raise ValueError(f"The installed drawing or ordering changed: {spans.keys()}")
    return images, dict(spans=spans, figures=figures)


def curve_overlap(lanes):
    """Count even an optimistic match ignoring clipping and device-space transforms."""
    import numpy as np
    from leo.presentation.fast_standard_analysis import PERIOD
    from leo.presentation.orbit_plot import _curve_samples
    from empty_bootstrap import clock, now

    start = now()
    bands = tuple(tuple(lane for lane in lanes if first <= int(lane.channel[2:]) <= last)
                  for first, last in ((1, 4), (5, 8)))
    keys = []
    for band in bands:
        digest = Counter()
        for lane in band:
            for curve in lane.curves:
                folded = np.asarray(_curve_samples(curve, PERIOD), dtype="<f8")
                digest[(curve.satellite_id, sha256(folded).hexdigest())] += 1
        keys.append(digest)
    return dict(counts=[sum(b.values()) for b in keys], matches=sum((keys[0] & keys[1]).values()),
                digest_work=clock(start))


def measure_case(case, installed, order):
    from empty_bootstrap import checked
    from exact_named_cairo_media import image_hashes
    from leo.contracts.fast_scan_orbits import PLOT_NAMES
    from PIL import Image

    root, scene_file, scene_pin, reference, reference_pin = CASES[case]
    packet, options = pickle.loads(checked(root/scene_file, scene_pin))
    expected = json.loads(checked(root/reference, reference_pin))["hashes"]["ordinary"]
    products, evidence = {}, {}
    for skip in order:
        name = "skip_first_restore" if skip else "ordinary"
        products[name], evidence[name] = orbit_draw(installed, packet, options, skip=skip)
        if image_hashes(products[name]) != expected:
            raise ValueError(f"{case} {name} must reproduce all eight archived ordinary PNGs")
    before, after = (evidence[mode] for mode in ("ordinary", "skip_first_restore"))
    if before["figures"] != after["figures"]:
        raise ValueError("The artist axes, titles or legend changed")
    one, two = before["figures"]
    equal_axes = [all(a[key] == b[key] for key in ("bbox", "xlim", "ylim", "xlabel", "ylabel"))
                  for a, b in zip(one["axes"], two["axes"], strict=True)]
    hashes = {}
    for name in PLOT_NAMES:
        with Image.open(BytesIO(products["ordinary"][name])) as a, Image.open(BytesIO(products["skip_first_restore"][name])) as b:
            ordinary, candidate = (sha256(image.convert("RGBA").tobytes()).hexdigest() for image in (a, b))
            if ordinary != candidate or (a.size, a.mode, a.info) != (b.size, b.mode, b.info):
                raise ValueError("Cropped or re-encoded orbit image")
            hashes[name] = dict(encoded=expected[name], rgba=ordinary, size=a.size, mode=a.mode, metadata=a.info)
    spans = before["spans"]
    budget = {key: dict(all_copy_restore=sum(row[key] for name in ("copy", "restore") for row in spans[name]),
        second_layout=spans["tight_layout"][1][key], second_axes=spans["subplots"][1][key],
        first_restores=sum(row[key] for row in spans["restore"][::2])) for key in ("cpu_s", "elapsed_s")}
    return dict(order=order, source_scene_sha256=scene_pin, ordinary_archive_sha256=reference_pin,
                counters=evidence, budget=budget, cross_band_axes_equal=equal_axes,
                curves=curve_overlap(packet["orbit_lanes"]), orbit_pngs=hashes)


def run(output):
    from empty_bootstrap import checked, load_runtime
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    _, spec, _, _, _ = load_runtime()
    from leo.presentation import orbit_plot
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout, shared_orbit_figures
    from aperture_trial import write

    for module in (orbit_plot, raster_layout, shared_orbit_figures):
        path = Path(module.__file__)
        checked(path, SOURCES[path.name])
    libs = []
    for name in ("png_filter", "png_deflate"):
        library = Path(spec[name]["library"])
        checked(library, spec[name]["sha256"])
        libs.append(library)
    renderer = partial(lossless_png.render_lossless_png, encoder=lossless_png.LosslessPng(libs[0], deflate_library=libs[1]))
    cases = {case: measure_case(case, renderer, order)
             for case, order in zip(CASES, ((False, True), (True, False)), strict=True)}
    write(output, dict(cases=cases, sources=SOURCES | {Path(__file__).name: sha256(Path(__file__).read_bytes()).hexdigest()},
                       waveform_reads=0, solver_runs=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    run(parser.parse_args().receipt)
