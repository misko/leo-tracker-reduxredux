"""Compare the full standard evidence path under a collapsed regional solver."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from PIL import Image

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.fast_standard_analysis import render
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_collapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "collapsed"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    scientific_packet = None
    original = algo08_position.selected_packet

    def selected_packet(*args):
        nonlocal scientific_packet
        scientific_packet = original(*args)
        return scientific_packet

    binding = algo08_collapsed.binding if args.mode == "collapsed" else nullcontext
    with binding(), patch.object(algo08_position, "selected_packet", selected_packet):
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, region)
    result.update(mode=args.mode, native_sha256=args.native_sha256, region=region.document())
    if args.render and scientific_packet is not None:
        start = process_time()
        figures = render(scientific_packet, title="Saved detector evaluation")
        result["render_cpu_s"] = process_time() - start
        for payload in figures.values():
            Image.open(BytesIO(payload)).verify()
        result["verified_figures"] = sorted(figures)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
