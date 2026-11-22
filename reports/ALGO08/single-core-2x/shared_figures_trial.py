"""Time both complete renderers against one full regional evidence packet."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import process_time, perf_counter
from unittest.mock import patch

from PIL import Image

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation import fast_standard_analysis as plots
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants.experimental.shared_orbit_figures import render_shared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("digest")
    parser.add_argument("title")
    parser.add_argument("--first", choices=("individual", "shared"), required=True)
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.digest:
        raise ValueError("Saved detector input changed")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    packets = []
    prepare = algo08_position.selected_packet

    def capture(*args):
        packet = prepare(*args)
        packets.append(packet)
        return packet

    with patch.object(algo08_position, "selected_packet", capture):
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer)
    if len(packets) != 1 or result["decision"]["status"] != "ok":
        raise ValueError("Expected a single complete scientific packet")
    packet, = packets
    individual = plots.render_fast_scan_orbits
    rows = []
    modes = ["individual", "shared"] if args.first == "individual" else ["shared", "individual"]
    for mode in modes + modes[::-1]:
        orbit = {}
        def timed(*args, **kwargs):
            start = process_time()
            images = (individual if mode == "individual" else render_shared)(*args, **kwargs)
            orbit["cpu_s"] = process_time() - start
            return images
        with patch.object(plots, "render_fast_scan_orbits", timed):
            cpu, wall = process_time(), perf_counter()
            images = plots.render(packet, title=args.title)
            cpu, wall = process_time()-cpu, perf_counter()-wall
        if len(images) != 8:
            raise ValueError("Incomplete figure set")
        hashes = {}
        for name, image in images.items():
            with Image.open(BytesIO(image)) as decoded:
                decoded.load()
            hashes[name] = sha256(image).hexdigest()
        rows.append(dict(mode=mode, render_cpu_s=cpu, render_wall_s=wall,
                         orbit_cpu_s=orbit["cpu_s"], sha256=hashes))
    print(json.dumps(dict(native_sha256=args.digest, region=offer.document(), observations=len(packet["observations"]),
                          title=args.title, rows=rows), indent=2))


if __name__ == "__main__":
    main()
