"""Profile outside the offer after stock selection, using sealed saved detections."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from leo.analysis.localization_v3.reassociation_context import objective
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants.experimental.exterior_profile import evaluate


def compare(native, archive, assets, region):
    prepare = algo08_position.prepare_packet
    audit = {}

    def profile(context, owners, *args, **kwargs):
        packet = prepare(context, owners, *args, **kwargs)
        original_grid = packet["position_grid"]
        if not original_grid["complete"]:
            raise ValueError("Need the complete original interior position grid")

        def score(arm, xy):
            return objective(context["problems"][arm][0], context, xy)

        started = process_time()
        audit.update(evaluate(context["scan"].search_region, original_grid, score))
        audit["extra_profile_cpu_s"] = process_time() - started
        return packet  # The diagnosis never enters the normal decision or artifacts.

    with patch.object(algo08_position, "prepare_packet", profile):
        result = measure("combined", native, archive, assets, region)
    if not audit or result["evidence"] is None:
        raise ValueError(f"No selected packet to test: {result['decision']['status']}")
    return dict(audit, decision=result["decision"]["status"],
                packet_arms=result["evidence"]["arms"],
                objective_replay=result["evidence"]["objective_replay"],
                complete_cpu_s=result["cpu_s"], orbit_policy=result["orbit_policy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "offer"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared SHA-256")
    region = Algo08Region.parse(json.loads(args.offer.read_bytes()))
    result = compare(json.loads(raw), TleArchiveReader(args.archive), args.assets, region)
    print(json.dumps(dict(result, region=region.document(), native_sha256=digest), allow_nan=False))


if __name__ == "__main__":
    main()
