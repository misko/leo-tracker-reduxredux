"""Run the grouped variational-kernel experiment on verified saved detections."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_bound_statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    with algo08_bound_statistics.group_statistics(algo08_position, args.library) as counters:
        receipt = measure("combined", json.loads(raw), TleArchiveReader(args.archive),
                          args.assets, region)
    print(json.dumps(dict(receipt, grouped_updates=counters, native_sha256=args.native_sha256,
                          region=region.document()), allow_nan=False))


if __name__ == "__main__":
    main()
