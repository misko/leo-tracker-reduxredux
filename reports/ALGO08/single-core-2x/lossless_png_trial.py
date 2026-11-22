"""Measure the eight guarded-layout PNGs against their saved publications."""

import argparse
import json
from functools import partial
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import mean
from time import perf_counter, process_time
from unittest.mock import patch

import matplotlib
import matplotlib.image
from PIL import Image
from PIL import __version__ as pillow_version

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse, algo08_salvage_statistics
from tools.pipeline_eval.variants.experimental import shared_orbit_figures
from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng, render_lossless_png
from tools.pipeline_eval.variants.experimental.raster_layout import render_layout

from .raster_layout_trial import compare


def _render(packet, title, encoder):
    encoding = []

    def measure(imsave):
        def save(*args, **kwargs):
            cpu = process_time()
            result = imsave(*args, **kwargs)
            encoding.append(process_time() - cpu)
            return result

        return save

    cpu, wall = process_time(), perf_counter()
    if encoder is None:
        with (
            patch.object(matplotlib.image, "imsave", measure(matplotlib.image.imsave)),
            patch.object(shared_orbit_figures, "imsave", measure(shared_orbit_figures.imsave)),
        ):
            images = render_layout(packet, title=title, require_trial=True)
    else:
        images = render_lossless_png(packet, title=title, require_trial=True, encoder=encoder)
        encoding = [row["encode_cpu_s"] for row in encoder.profile]
    cpu, wall = process_time() - cpu, perf_counter() - wall
    fast = encoder.profile if encoder is not None else []
    if len(encoding) != 8 or (encoder is not None and len(fast) != 8):
        raise ValueError("Expected all eight images from the selected encoder")
    return images, dict(
        cpu_s=cpu,
        wall_s=wall,
        encoding_cpu_s=sum(encoding),
        draw_cpu_s=cpu - sum(encoding),
        encoding_calls_cpu_s=encoding,
        encoder_calls=fast,
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        payload_bytes=sum(map(len, images.values())),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("detections", "pair", "archive", "assets"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--level", type=int, default=3)
    parser.add_argument("--scalar", action="store_true")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    native = args.detections.read_bytes()
    if sha256(native).hexdigest() != args.native_sha256:
        raise ValueError("Saved detection bytes differ")
    pair = json.loads(args.pair.read_bytes())
    offer = Algo08Region.parse(json.loads(Path(pair["region"]).read_bytes()))
    with (
        patch.object(
            algo08_position,
            "prepare_native_scan",
            partial(
                algo08_causal_reuse.prepare, algo08_position.prepare_native_scan, statistics={}
            ),
        ),
        algo08_salvage_statistics.salvage_statistics(),
    ):
        decision, packet, _ = algo08_position.solve(
            json.loads(native), TleArchiveReader(args.archive), args.assets, offer
        )
    baseline = pair["runs"]["baseline"]
    if decision["status"] != "ok" or not packet:
        raise ValueError("Expected a complete scientific packet")
    if {arm: row["endpoint_latlon"] for arm, row in packet["arms"].items()} != {
        arm: row["latlon"] for arm, row in baseline["arms"].items()
    }:
        raise ValueError("Reconstructed packet does not reproduce both published coordinates")

    peak_before_render = getrusage(RUSAGE_SELF).ru_maxrss
    title = Path(pair["recording"]).name
    previous, measurements = None, []
    for _ in range(args.repeats):
        encoder = (
            LosslessPng(args.library.resolve(), level=args.level, simd=not args.scalar, profile=[])
            if args.library
            else None
        )
        images, timing = _render(packet, title, encoder)
        if previous is not None and images != previous:
            raise ValueError("Nondeterministic outputs from renderer")
        previous = images
        measurements.append(timing)

    store = FastStandardAnalysisStore(args.pair.parent / "baseline")
    publication = {
        entry["name"]: store.artifact(baseline["receipt"]["run_id"], entry["name"], entry["sha256"])
        for entry in baseline["artifacts"]
    }
    for payload in images.values():
        with Image.open(BytesIO(payload)) as image:
            image.verify()
    figures = compare(publication, images)
    if not args.library and not all(info["bytes_match"] for info in figures.values()):
        raise ValueError("Control must reproduce the published PNG bytes")
    print(
        json.dumps(
            dict(
                title=title,
                detection_sha256=args.native_sha256,
                session=baseline["receipt"]["session_id"],
                matplotlib=matplotlib.__version__,
                pillow=pillow_version,
                encoder="libdeflate" if args.library else "pillow",
                level=args.level if args.library else 6,
                simd=bool(args.library and not args.scalar),
                library_sha256=sha256(args.library.read_bytes()).hexdigest()
                if args.library
                else None,
                region=offer.document(),
                arms=packet["arms"],
                observations=len(packet["observations"]),
                peak_before_render_kib=peak_before_render,
                measurements=measurements,
                mean_cpu_s=mean(row["cpu_s"] for row in measurements),
                figures=figures,
            ),
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
