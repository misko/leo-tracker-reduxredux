"""Audit sealed DS30-0402 pixels and test the exact ordinary panel geometry on a saved scene."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import pickle
from time import process_time_ns
from unittest.mock import patch

import numpy as np
from PIL import Image
from scipy.ndimage import maximum_filter

import direct_orbit_figures as cairo
from named_weak_visual import registered_orbits


HISTORY = Path("/dev/shm/leo-v3-history-risk-cairo-0402-result01")
ORDINARY = Path("/dev/shm/leo-v3-history-risk-0402-pair01-routed")
SCORE = "82a177ef8ea46681c9021ab830cdaa7f737f1ad633f644890a06ce742aac239f"
DENSE = Path("/dev/shm/leo-direct-orbits-dense-01/native/orbit-lanes.pickle")
DENSE_SHA = "6f54db7a09e0f79c9eaa92c7d41bf2b38c49b2da06ba976be737edcdfd6800c0"
REGISTRATION_SIZE = (2160, 246)


def checked(path, sha):
    data = path.read_bytes()
    if sha256(data).hexdigest() != sha.removeprefix("sha256:"):
        raise ValueError(f"Sealed publication input changed: {path}")
    return data


def neutral(image, maximum_chroma=0):
    return (np.ptp(image, axis=2) <= maximum_chroma) & (image[..., 0] <= 172)


def explain_gray(source, peer):
    crop = np.zeros(source.shape[:2], dtype=bool)
    crop[3:-3, 3:-3] = True
    reference = neutral(peer)
    src = neutral(source) & crop
    misses = src & ~maximum_filter(reference & crop, size=5, mode="constant")
    outside_crop = misses & maximum_filter(reference, size=5, mode="constant")
    tinted = misses & ~outside_crop & maximum_filter(neutral(peer, 15), size=5, mode="constant")
    return dict(pixels=int(src.sum()), misses=int(misses.sum()), outside_crop=int(outside_crop.sum()),
                nearby_tint=int(tinted.sum()), unresolved=int((misses & ~outside_crop & ~tinted).sum()))


def actual_pixels():
    score = json.loads(checked(HISTORY / "verified-result.json", SCORE))
    render = json.loads((HISTORY / "render.json").read_bytes())
    if render != score["cairo"]:
        raise ValueError("The artist evidence changed after the publication audit")
    old, new = "ordinary", "cairo"
    results = {}
    for name, evidence in score["registration"].items():
        rasters = []
        for arm, root in ((old, ORDINARY), (new, HISTORY)):
            digest = score["media"][name][arm]["sha256"]
            (path,) = (root / "candidate/fast-scan-standard-v2").glob("*/*/" + digest[7:] + ".png")
            with Image.open(BytesIO(checked(path, digest))) as png:
                rasters.append(png.convert("RGB"))
        registered = registered_orbits(*rasters, require_match=False)
        if json.loads(json.dumps(registered)) != evidence:
            raise ValueError("Stored registration failed to replay")
        rows = []
        for panel, boxes in enumerate(zip(*evidence["boxes"], strict=True)):
            a, b = (np.asarray(im.transform(REGISTRATION_SIZE, Image.Transform.EXTENT, box, Image.Resampling.NEAREST))
                    for im, box in zip(rasters, boxes, strict=True))
            diagnostic = {old: explain_gray(a, b), new: explain_gray(b, a)}
            heights = [box[3] - box[1] for box in boxes]
            rows.append(dict(height=heights, strict=registered["rows"][panel], diagnostic=diagnostic))
        artist_index = 0 if name.startswith("ch1-4") else 1
        results[name] = dict(lanes=rows, artist=render["artists"]["orbit"][artist_index],
                             evidence=score["media"][name])
    return results


def source_geometry(figure):
    """Convert the original axes' display boxes from the bottom to the top origin."""
    height = int(figure.bbox.height)
    boxes = [(float(left), float(height - top), float(right - left), float(top - bottom))
             for left, bottom, right, top in (ax.bbox.extents for ax in figure.axes)]
    if int(figure.bbox.width) != cairo.WIDTH or not boxes or any(w <= 0 or h <= 0 for _, _, w, h in boxes):
        raise ValueError("Expected the original orbit panel template")
    return height, boxes


def dense_scene(path):
    from tools.pipeline_eval.variants.experimental import shared_orbit_figures as stock

    lanes, options = pickle.loads(checked(path, DENSE_SHA))
    start = process_time_ns()
    plots = cairo.scene(lanes, **options)
    cairo_scene = process_time_ns() - start
    placement = []
    construction = 0
    original = stock.make_orbit_plot

    def capture(*args, **kwargs):
        nonlocal construction
        start = process_time_ns()
        fig = original(*args, **kwargs)
        placement.append(source_geometry(fig))
        construction += process_time_ns() - start
        return fig

    started = process_time_ns()
    with patch.object(stock, "make_orbit_plot", capture):
        pngs = stock.render_shared(lanes, **options, reuse_pixels=True)
    ordinary_cpu = process_time_ns() - started

    def paint(aligned):
        clock = process_time_ns()
        products = {}
        for (prefix, plot), shape in zip(plots.items(), placement, strict=True):
            if len(shape[1]) != len(plot["rows"]):
                raise ValueError("The ordinary geometry and Cairo data lanes differ")

            def geometry(plot):
                return shape if aligned else native_geometry(plot)

            def ticks(plot, _):
                return native_ticks(plot, native_box)

            native_box = native_geometry(plot)[1][0]
            with patch.object(cairo, "geometry", geometry), patch.object(cairo, "lane_ticks", ticks):
                views, _ = cairo.raster(plot, cairo.library(), lambda rgba: Image.fromarray(rgba).convert("RGB"))
            products.update({prefix + "-" + name: image for name, image in views.items()})
        return products, process_time_ns() - clock

    native_geometry, native_ticks = cairo.geometry, cairo.lane_ticks
    native, native_cpu = paint(False)
    aligned, aligned_cpu = paint(True)
    scores = {}
    for name, png in pngs.items():
        with Image.open(BytesIO(png)) as ordinary:
            source = ordinary.convert("RGB")
            if source.size != native[name].size or source.size != aligned[name].size:
                raise ValueError("Prototype changed published image dimensions")
            scores[name] = {mode: registered_orbits(source, images[name], require_match=False)
                            for mode, images in (("cairo", native), ("aligned", aligned))}
    row_ids = tuple((lane.receiver, lane.channel) for lane in lanes)
    return dict(archive_sha256=DENSE_SHA, bands=list(plots), lane_ids=row_ids, cpu_ns=dict(
                    ordinary_with_png=ordinary_cpu, ordinary_geometry=construction, cairo_scene=cairo_scene,
                    cairo_without_png=native_cpu, aligned_without_png=aligned_cpu),
                scores=scores)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    result = dict(actual_0402=actual_pixels(), independent_0008=dense_scene(DENSE),
                  controls=dict(sealed_publication_sha256=SCORE, code_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    with args.receipt.open("x") as handle:
        json.dump(result, handle, sort_keys=True, allow_nan=False, indent=2)
        handle.write("\n")
