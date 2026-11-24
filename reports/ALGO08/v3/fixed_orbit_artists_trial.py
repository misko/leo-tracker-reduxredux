"""Compare the frozen Agg orbit renderer and its fixed-view artist setup."""

import argparse
from collections import defaultdict
from contextlib import nullcontext
from functools import partial
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import pickle
import sys
from unittest.mock import patch

from empty_bootstrap import checked, clock, now
from ordinary_orbit_reuse import CASES, SOURCES, layout_fields


HERE = Path(__file__).resolve().parent
DENSE_CONTROL = Path("/dev/shm/leo-cumulative-grid-projection-01/dense-pair/installed")
DENSE_CONTROL_SHA = "36fa0878285a89b94d5bd4adb1b5a90285dcf6e5b1904a3ae7502f669ef7e895"


def compare_pngs(control, candidate, *, published=None):
    from named_weak_visual import registered_orbits
    from PIL import Image

    with Image.open(BytesIO(control)) as a, Image.open(BytesIO(candidate)) as b:
        if (a.size, a.mode, a.info) != (b.size, b.mode, b.info):
            raise ValueError("Orbit PNG layout, mode or metadata changed")
        original = sha256(a.convert("RGBA").tobytes()).hexdigest()
        if original != sha256(b.convert("RGBA").tobytes()).hexdigest() or control != candidate:
            raise ValueError("Candidate changed the encoded orbit PNG or its decoded raster")
        registration = registered_orbits(a.convert("RGB"), b.convert("RGB"))
        archive = None
        if published is not None:
            with Image.open(BytesIO(published)) as old:
                if (a.size, a.mode, a.info) != (old.size, old.mode, old.info):
                    raise ValueError("The replay disagrees with the published PNG metadata")
                archive = dict(encoded=sha256(published).hexdigest(),
                               rgba=sha256(old.convert("RGBA").tobytes()).hexdigest())
                if original != archive["rgba"]:
                    raise ValueError("The replay disagrees with the published orbit pixels")
        return dict(sha256=sha256(control).hexdigest(), rgba=original, size=a.size, mode=a.mode,
                    metadata=a.info, encoded_bytes=len(control), registration=registration, archive=archive)


def dense_archive():
    from leo.contracts.fast_scan_orbits import PLOT_NAMES
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    worker = json.loads(checked(DENSE_CONTROL / "cumulative-grid-worker.json", DENSE_CONTROL_SHA))
    receipt = worker["receipt"]
    store = FastStandardAnalysisStore(DENSE_CONTROL)
    run_id = receipt["run_id"]
    detail = store.detail(run_id)
    if detail["state"] != "complete" or detail["terminal_sha256"] != receipt["terminal_sha256"]:
        raise ValueError("Reference is not the original published dense fix")
    return {row["name"]: store.artifact(run_id, row["name"], row["sha256"])
            for row in detail["artifacts"] if row["name"] in PLOT_NAMES}


def render(installed, encoder, source, options, *, fixed, bundle):
    from fixed_orbit_artists import fixed_artists
    from leo.presentation import orbit_plot
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from tools.pipeline_eval.variants.experimental import raster_layout, shared_orbit_figures as shared

    spans, figures = defaultdict(list), []
    calls = None
    original_render = raster_layout.render_shared

    def timed(name, operation):
        def call(*args, **kwargs):
            start = now()
            result = operation(*args, **kwargs)
            spans[name].append(clock(start))
            return result
        return call

    def measure(lanes, **settings):
        nonlocal calls
        scope = fixed_artists(lanes, raster_layout=raster_layout, **settings) if fixed else nullcontext()
        make = timed("make", shared.make_orbit_plot)

        def build(*args, **kwargs):
            figure = make(*args, **kwargs)
            figures.append(timed("layout_witness", layout_fields)(figure))
            return figure

        with (scope as calls, patch.object(shared, "make_orbit_plot", build),
              patch.object(FigureCanvasAgg, "draw", timed("agg_base", FigureCanvasAgg.draw)),
              patch.object(FigureCanvasAgg, "copy_from_bbox", timed("copy", FigureCanvasAgg.copy_from_bbox)),
              patch.object(FigureCanvasAgg, "restore_region", timed("restore", FigureCanvasAgg.restore_region)),
              patch.object(shared, "imsave", timed("encode", shared.imsave))):
            return original_render(lanes, **settings)

    wrap = timed("orbit", measure)
    if bundle:
        with patch.object(raster_layout, "render_shared", wrap):
            images = timed("bundle", installed)(source, require_trial=True, **options)
    else:
        with (patch.object(orbit_plot, "Figure", raster_layout._OrbitFigure),
              patch.object(shared, "imsave", encoder.wrap(shared.imsave))):
            images = wrap(source, reuse_pixels=True, **options)
    expected = {"make": 2, "layout_witness": 2, "agg_base": 2, "copy": 2, "restore": 4, "encode": 4, "orbit": 1}
    if any(len(spans[stage]) != count for stage, count in expected.items()):
        raise ValueError("The ordinary shared Agg execution changed")
    if fixed and (calls is None or calls["figures"] != 2 or calls["axes"] != 16 or not calls["scatters"]):
        raise ValueError("The fixed-view route did not run")
    return images, dict(spans=spans, figures=figures, fixed=calls)


def run_case(label, installed, encoder, *, orders):
    from exact_named_cairo_media import image_hashes
    from leo.contracts.fast_scan_orbits import PLOT_NAMES
    from orbit_gray_layout_trial import DENSE, DENSE_SHA

    bundle = label != "DS30-0008"
    if bundle:
        root, path, scene_pin, ref, ref_pin = CASES[label]
        source, options = pickle.loads(checked(root / path, scene_pin))
        expected = json.loads(checked(root / ref, ref_pin))["hashes"]["ordinary"]
        archive = {}
    else:
        scene_pin, ref_pin = DENSE_SHA, DENSE_CONTROL_SHA
        source, options = pickle.loads(checked(DENSE, scene_pin))
        expected = None
        archive = dense_archive()
        if set(archive) != set(PLOT_NAMES):
            raise ValueError("Archival dense reference has missing orbit products")
    products = witness = None
    clocks = []
    for order in orders:
        fresh = {}
        evidence = {}
        for mode in order:
            fresh[mode], evidence[mode] = render(installed, encoder, source, options, fixed=mode == "fixed", bundle=bundle)
            if expected is not None and image_hashes(fresh[mode]) != expected:
                raise ValueError(f"{label} {mode} does not reproduce its original eight ordinary PNGs")
        if fresh["ordinary"] != fresh["fixed"] or (products is not None and products != fresh["fixed"]):
            raise ValueError(f"{label} output changed in the matched render or reverse order")
        if evidence["ordinary"]["figures"] != evidence["fixed"]["figures"] or (
                witness is not None and witness != evidence["fixed"]["figures"]):
            raise ValueError(f"{label} live axes, titles or legend changed")
        products, witness = fresh["fixed"], evidence["fixed"]["figures"]
        clocks.append(dict(order=order, timings={mode: rows["spans"] for mode, rows in evidence.items()},
                           fixed=evidence["fixed"]["fixed"]))
    return dict(scene_sha256=scene_pin, archive_sha256=ref_pin, clocks=clocks, live_geometry=witness,
                media={name: compare_pngs(fresh["ordinary"][name], products[name], published=archive.get(name))
                       for name in PLOT_NAMES},
                ancillary_hashes={key: value for key, value in image_hashes(products).items() if key not in PLOT_NAMES})


def run(output):
    from empty_bootstrap import load_runtime
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    _, spec, _, _, _ = load_runtime()
    from aperture_trial import write
    from leo.presentation import orbit_plot
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout, shared_orbit_figures

    for module in (orbit_plot, raster_layout, shared_orbit_figures):
        path = Path(module.__file__)
        checked(path, SOURCES[path.name])
    libs = []
    for key in ("png_filter", "png_deflate"):
        path = Path(spec[key]["library"])
        checked(path, spec[key]["sha256"])
        libs.append(path)
    encoder = lossless_png.LosslessPng(libs[0], deflate_library=libs[1])
    if encoder.libraries is None:
        raise ValueError("Expected the frozen lossless PNG encoder")
    installed = partial(lossless_png.render_lossless_png, encoder=encoder)
    forward, reverse = ("ordinary", "fixed"), ("fixed", "ordinary")
    cases = {label: run_case(label, installed, encoder, orders=orders) for label, orders in (
        ("DS30-0402", (forward, reverse)), ("DS30-0008", (reverse, forward)), ("DS30-0016", (forward, reverse)))}
    write(output, dict(cases=cases, sources=SOURCES | {
        name: sha256((HERE / name).read_bytes()).hexdigest() for name in
        ("agg-orbit-artists-protocol.md", "fixed_orbit_artists.py", "fixed_orbit_artists_trial.py")},
                       encoder={key: spec[key] for key in ("png_filter", "png_deflate")}, waveform_reads=0, solver_runs=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    run(parser.parse_args().receipt)
