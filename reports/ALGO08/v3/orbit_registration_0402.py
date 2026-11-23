"""Localize the failed named DS30-0402 gray pixel counts without plotting."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import label, maximum_filter

from leo.analysis.localization_v3.tracks import winning_observations


MODES = ("fitted-first", "combined")
SHEETS = ("ch1-4-all", "ch1-4-unassociated")
PANEL = 3
SIZE = (2160, 246)


def sealed_bytes(path, expected=None):
    data = path.read_bytes()
    pin = sha256(data).hexdigest()
    if expected is not None and pin != expected.removeprefix("sha256:"):
        raise ValueError(f"Published artifact failed its content address: {path}")
    return data, pin


def observations(root):
    sources, owned = {}, {}
    for mode in MODES:
        (native,) = (root / mode / "fast-scan-automatic-work").glob("*/detections.json")
        data, pin = sealed_bytes(native)
        sources[mode] = pin
        receipt = json.loads((root / mode / "named-constrained-research.json").read_bytes())
        owned[mode] = receipt["selected_rows"]["fitted_c"]
    if sources[MODES[0]] != sources[MODES[1]] or owned[MODES[0]] != owned[MODES[1]]:
        raise ValueError("The two arms published different factor or ordered owner rows")
    points, _ = winning_observations(json.loads(data))
    lane = [point for point in points if (point["receiver"], point["channel"]) == (1, 2)]
    ids = {obs for obs, _, _ in owned[MODES[1]]}
    loose = [point for point in lane if point["observation_id"] not in ids]
    return len(points), len(lane), loose, sources


def registered(root, score, sheet):
    pixels = []
    for mode, boxes in zip(MODES, score["registration"][sheet]["boxes"], strict=True):
        pin = score["runs"][mode]["figures"][sheet]["sha256"]
        (path,) = (root / mode / "fast-scan-standard-v2").glob("*/*/" + pin[7:] + ".png")
        raw, _ = sealed_bytes(path, pin)
        with Image.open(BytesIO(raw)) as image:
            crop = image.convert("RGB").transform(SIZE, Image.Transform.EXTENT, boxes[PANEL-1], Image.Resampling.NEAREST)
            pixels.append(np.array(crop))
    return pixels


def gray(mask, slack=0):
    return (np.ptp(mask, axis=2) <= slack) & (mask[..., 0] <= 172)


def misses(source, peer, loose):
    interior = np.zeros(source.shape[:2], dtype=bool)
    interior[3:-3, 3:-3] = True
    one, other = gray(source) & interior, gray(peer) & interior
    diff = one & ~maximum_filter(other, size=5, mode="constant")
    clusters, size = label(diff, np.ones((3, 3)))
    groups = []
    for index in range(1, size+1):
        points = np.argwhere(clusters == index)
        y, x = np.round(points.mean(axis=0)).astype(int)
        seconds = (float(x) + .5) * 300 / SIZE[0]
        observed = min(loose, key=lambda row: abs(row["time_s"] - seconds))
        groups.append(dict(pixels=len(points), xy=[int(x), int(y)], time_s=seconds,
                           nearest_loose_time_s=observed["time_s"], nearest_loose_id=observed["observation_id"],
                           nearest_loose_dx_px=(seconds-observed["time_s"])*SIZE[0]/300,
                           stock_or_native_rgb=peer[y, x].tolist()))
    edge = diff & maximum_filter(gray(peer), size=5, mode="constant")
    mixed = diff & ~edge & maximum_filter(gray(peer, slack=15), size=5, mode="constant")
    remaining = diff & ~edge & ~mixed
    return dict(gray_pixels=int(one.sum()), unmatched_pixels=int(diff.sum()), strict_fraction=1-float(diff.sum()/one.sum()),
                cropped_neighbor_pixels=int(edge.sum()), nearby_low_chroma_pixels=int(mixed.sum()),
                remaining_after_diagnostics=int(remaining.sum()), groups=groups)


def analyze(root, score_path):
    raw, pin = sealed_bytes(score_path)
    score = json.loads(raw)
    points, lane, loose, sources = observations(root)
    results = {}
    for sheet in SHEETS:
        control, native = registered(root, score, sheet)
        directions = [misses(control, native, loose), misses(native, control, loose)]
        original = score["registration"][sheet]["rows"][PANEL-1]["gray"]
        if (original["pixels"] != [d["gray_pixels"] for d in directions]
                or not np.allclose(original["fraction"], [d["strict_fraction"] for d in directions], rtol=0, atol=2e-16)):
            raise ValueError("The diagnostic did not reproduce the frozen panel scores")
        results[sheet] = dict(agg_to_cairo=directions[0], cairo_to_agg=directions[1])
    return dict(scoring_sha256=pin, native_sha256=sources, points=points, lane_points=lane,
                lane="RX1 CH2", gray_lane_points=len(loose), frozen_visual_pass=score["visual_pass"],
                failed_layers=score["failed_layers"], original_registration=score["registration"], diagnostic=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publication", type=Path)
    parser.add_argument("scored_receipt", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.publication, args.scored_receipt), indent=2, allow_nan=False))
