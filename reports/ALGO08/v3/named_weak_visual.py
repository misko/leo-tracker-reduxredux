"""Audit the stored named and Cairo charts without rerunning the solve."""

import argparse
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import maximum_filter


ORBIT_SATELLITES = ("63510", "64015")  # Both archived named orbit-sheet legends.


def orbit_boxes(rgb):
    dark = rgb.max(axis=2) <= 100
    rows = np.flatnonzero(dark.sum(axis=1) > .8 * rgb.shape[1])
    spines = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)
    if len(spines) != 16:
        raise ValueError("Expected eight pairs of orbit panel spines")
    for top, bottom in zip(spines[::2], spines[1::2], strict=True):
        columns = np.flatnonzero(dark[top].any(axis=0))
        yield float(columns[0] + .5), float(top.mean()), float(columns[-1] + .5), float(bottom.mean())


def support(left, right):
    counts = [int(mask.sum()) for mask in (left, right)]
    if any(counts) and not all(counts):
        raise ValueError("One renderer omitted a visible orbit layer")
    if not all(counts):
        return dict(pixels=counts, fraction=None)
    fractions = [float(np.count_nonzero(a & maximum_filter(b, size=5, mode="constant")) / n)
                 for a, b, n in ((left, right, counts[0]), (right, left, counts[1]))]
    return dict(pixels=counts, fraction=fractions)


def registered_orbits(control, native, *, require_match=True):
    boxes = tuple(list(orbit_boxes(np.asarray(image))) for image in (control, native))
    rows = []
    for limits in zip(*boxes, strict=True):
        scaled = [image.transform((2160, 246), Image.Transform.EXTENT, box, Image.Resampling.NEAREST)
                  for image, box in zip((control, native), limits, strict=True)]
        pixels = [np.asarray(image)[3:-3, 3:-3] for image in scaled]
        chroma = [np.ptp(data, axis=2) for data in pixels]
        color = support(*(data >= 32 for data in chroma))
        gray = support(*((shade == 0) & (data[..., 0] <= 172) for data, shade in zip(pixels, chroma, strict=True)))
        for layer in (color, gray):
            if require_match and layer["fraction"] is not None and min(layer["fraction"]) < .98:
                raise ValueError("Registered orbit data differ at two-pixel tolerance")
        rows.append(dict(color=color, gray=gray))
    return dict(boxes=boxes, rows=rows)


def verify_legend(native):
    from matplotlib import colormaps
    from direct_orbit_figures import GRAY, legend, legend_columns, library, surface

    palette = colormaps["turbo"]
    entries = [("Unassociated", GRAY), *((sat, palette((i + .5) / len(ORBIT_SATELLITES))[:3])
                                         for i, sat in enumerate(ORBIT_SATELLITES))]
    c, height = library(), native.height
    last = height * .975 - 24
    banner = slice(int(last - 26), int(last + 12))
    with surface(c, height) as (canvas, surface_id, pixels):
        canvas.ink(1., 1., 1.)
        c.cairo_paint(canvas.ctx)
        legend(canvas, entries, height)
        c.cairo_surface_flush(surface_id)
        columns = list(legend_columns(entries, canvas.text_width))
        gaps = [float(x1 - x0 - 46 - max(canvas.text_width(entries[i][0], 8) for i in group))
                for (x0, group), (x1, _) in zip(columns, columns[1:])]
        if min(gaps) < 20 or not np.array_equal(pixels[banner, :, 2::-1], np.asarray(native)[banner]):
            raise ValueError("The candidate orbit legend differs from the named label inventory")
    return dict(labels=[name for name, _ in entries], minimum_gap_px=min(gaps))


def audit(root, result):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    modes = ("control", "candidate")
    stores = [FastStandardAnalysisStore(root / mode) for mode in modes]
    runs = result["runs"]
    report = {}
    for name in runs["control"]["images"]:
        pair = [store.artifact(runs[mode]["trace"]["publication"]["run_id"], name,
                               runs[mode]["images"][name]["sha256"])
                for mode, store in zip(modes, stores, strict=True)]
        with Image.open(BytesIO(pair[0])) as left, Image.open(BytesIO(pair[1])) as right:
            if left.size != right.size:
                raise ValueError(f"Publication dimensions differ for {name}")
            row = dict(pixels=list(left.size), encoded_bytes=dict(zip(modes, map(len, pair), strict=True)))
            if name.endswith(("-all", "-unassociated")):
                control, native = (image.convert("RGB") for image in (left, right))
                row.update(**registered_orbits(control, native), legend=verify_legend(native))
        report[name] = row
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = json.loads((args.root / "result.json").read_bytes())
    print(json.dumps(audit(args.root, result), indent=2, sort_keys=True, allow_nan=False))
