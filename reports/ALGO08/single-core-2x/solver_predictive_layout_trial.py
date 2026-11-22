"""Time predictive layouts through the selected full variational grid."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools.pipeline_eval.variants import algo08_predictive_layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "prepared"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    with algo08_predictive_layout.measured_prediction(enabled=args.mode == "prepared") as counters:
        result = measure(
            "combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, region,
        )
    result.update(mode=args.mode, prediction=dict(counters),
                  native_sha256=args.native_sha256, region=region.document())
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
