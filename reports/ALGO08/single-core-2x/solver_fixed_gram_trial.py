"""Compare fixed track Gram reuse through robust fitting and full grid publication."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_endpoint_readout, algo08_fixed_gram, v5_direct_cavity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "fixed", "mapped", "observe", "readout"))
    for name in ("native", "archive", "assets", "region", "library"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    readout = args.mode in ("observe", "readout")
    scope = (algo08_endpoint_readout.measured_readout(v5_direct_cavity, reuse=args.mode == "readout")
             if readout else nullcontext())
    with (
        scope as endpoint_counts,
        algo08_fixed_gram.measured_backend(
            algo08_position, args.library, mode="control" if readout else args.mode
        ) as native_stats,
    ):
        result = measure(
            "combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, region,
        )
    result.update(mode=args.mode, native_stats=native_stats, endpoint_counts=endpoint_counts,
                  native_sha256=args.native_sha256, region=region.document())
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
