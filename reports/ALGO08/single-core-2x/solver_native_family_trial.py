"""Time baseline and native family-Schur ALGO08v2 math on saved detections."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_native_family


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--library", type=Path)
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    with algo08_native_family.measured_backend(algo08_position, args.library) as native_metrics:
        results = measure("combined", json.loads(raw), TleArchiveReader(args.archive),
                          args.assets, offer)
    print(json.dumps(dict(results, native_metrics=native_metrics, native_sha256=args.native_sha256,
                          region=offer.document()), allow_nan=False))


if __name__ == "__main__":
    main()
