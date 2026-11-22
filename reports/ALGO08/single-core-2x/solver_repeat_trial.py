"""Run a saved-input solver comparison with fixed-problem exact evaluation reuse."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools.pipeline_eval.variants.algo08_fit_reuse import repeated_fit_points
from solver_trial import measure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.native_sha256:
        raise ValueError("Saved detector authority changed")
    counters = Counter()
    with repeated_fit_points(counters):
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets,
                         Algo08Region.parse(json.loads(args.region.read_bytes())))
    print(json.dumps(dict(result, reuse=counters, native_sha256=args.native_sha256), allow_nan=False))


if __name__ == "__main__":
    main()
