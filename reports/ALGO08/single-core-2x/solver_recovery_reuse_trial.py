"""Check unchanged paired recovery fits using the saved-detection solver benchmark."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools.pipeline_eval.variants.algo08_recovery_reuse import stable_recovery


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "reuse"))
    for field in ("native", "archive", "assets", "offer"):
        parser.add_argument(field, type=Path)
    parser.add_argument("digest")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.digest:
        raise ValueError("Unexpected saved detector digest")
    offer = Algo08Region.parse(json.loads(args.offer.read_bytes()))
    with stable_recovery() if args.mode == "reuse" else nullcontext({}) as counts:
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer)
    result.update(mode=args.mode, gate_counts=counts, native_sha256=args.digest, region=offer.document())
    print(json.dumps(result, allow_nan=False))
