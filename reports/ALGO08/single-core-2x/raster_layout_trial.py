"""Compare complete renderers on each already qualified detection packet."""

import argparse
import json
from functools import partial
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import matplotlib
from PIL import Image, ImageChops

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse, algo08_salvage_statistics
from tools.pipeline_eval.variants.experimental.raster_layout import (
    render_layout,
    render_shared_pixels,
)


def compare(control, trial):
    comparison = {}
    if control.keys() != trial.keys() or len(control) != 8:
        raise ValueError("Expected all eight publication PNGs")
    for name, reference in control.items():
        candidate = trial[name]
        with (Image.open(BytesIO(reference)) as left, Image.open(BytesIO(candidate)) as right):
            left.load()
            right.load()
            if left.format != "PNG" or right.format != "PNG":
                raise ValueError(f"Expected PNG for {name}")
            dimensions_match = left.size == right.size and left.mode == right.mode
            pixels_match = dimensions_match and not ImageChops.difference(left, right).getbbox(
                alpha_only=False,
            )
            if not pixels_match or left.info != right.info:
                raise ValueError(f"Decoded publication changed for {name}")
            comparison[name] = dict(
                width=left.width, height=left.height, mode=left.mode,
                metadata=left.info, decoded_pixels_match=pixels_match,
                bytes_match=reference == candidate, bytes_control=len(reference),
                bytes_trial=len(candidate), sha256_control=sha256(reference).hexdigest(),
                sha256_trial=sha256(candidate).hexdigest(),
            )
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("detections", "pair", "archive", "assets"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--first", choices=("shared-pixels", "layout"), required=True)
    args = parser.parse_args()
    native = args.detections.read_bytes()
    if sha256(native).hexdigest() != args.native_sha256:
        raise ValueError("Saved detection bytes differ")
    pair = json.loads(args.pair.read_bytes())
    offer = Algo08Region.parse(json.loads(Path(pair["region"]).read_bytes()))
    with (patch.object(algo08_position, "prepare_native_scan", partial(
            algo08_causal_reuse.prepare, algo08_position.prepare_native_scan, statistics={})),
          algo08_salvage_statistics.salvage_statistics()):
        decision, packet, _ = algo08_position.solve(
            json.loads(native), TleArchiveReader(args.archive), args.assets, offer)
    if decision["status"] != "ok" or not packet:
        raise ValueError("Expected a complete scientific packet")
    baseline = pair["runs"]["baseline"]
    endpoints = {arm: row["endpoint_latlon"] for arm, row in packet["arms"].items()}
    if endpoints != {arm: row["latlon"] for arm, row in baseline["arms"].items()}:
        raise ValueError("Reconstructed packet does not reproduce both published coordinates")
    title = Path(pair["recording"]).name
    renderers = {
        "shared-pixels": render_shared_pixels,
        "layout": partial(render_layout, require_trial=True),
    }
    second, = renderers.keys() - {args.first}
    results, timings = {}, []
    for name in (args.first, second, second, args.first):
        cpu, wall = process_time(), perf_counter()
        images = renderers[name](packet, title=title)
        timings.append(dict(renderer=name, cpu_s=process_time()-cpu, wall_s=perf_counter()-wall))
        if name in results and images != results[name]:
            raise ValueError(f"Nondeterministic outputs from {name}")
        results[name] = images
    comparison = compare(results["shared-pixels"], results["layout"])
    if {name: "sha256:" + row["sha256_control"] for name, row in comparison.items()} != {
            row["name"]: row["sha256"] for row in baseline["artifacts"]}:
        raise ValueError("Shared-pixel control differs from the released publication")
    print(json.dumps(dict(
        title=title, native_sha256=args.native_sha256, matplotlib=matplotlib.__version__,
        region=offer.document(), arms=packet["arms"], observations=len(packet["observations"]),
        timings=timings, figures=comparison,
    ), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
