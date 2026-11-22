"""Compare temporal trust proposals against the full saved-detection solver."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_temporal_trust, v5_direct_cavity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "temporal"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    audit, owners = {}, {}
    selected_packet = algo08_position.selected_packet

    def packet(*values):
        evidence = selected_packet(*values)
        for arm, rows in evidence["rows"].items():
            owners[arm] = {row["observation_id"]: int(row["norad"]) for row in rows}
            if len(owners[arm]) != len(rows):
                raise ValueError("Duplicate IDs in the selected evidence packet")
        return evidence

    optimizer = partial(algo08_temporal_trust.optimizer, args.mode == "temporal", audit)
    with (
        patch.object(v5_direct_cavity, "bounded_secant", optimizer),
        patch.object(algo08_position, "selected_packet", packet),
    ):
        result = measure(
            "combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer
        )
    result.update(mode=args.mode, optimizer=audit, owners=owners,
                  native_sha256=args.native_sha256, region=offer.document())
    print(json.dumps(result, default=_json_value, allow_nan=False))


if __name__ == "__main__":
    main()
