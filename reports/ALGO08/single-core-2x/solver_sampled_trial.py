"""Compare sampled initial search through full evidence on saved detections."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from leo.analysis.localization_v3 import discovery
from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_sampled_initial, v5_core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "sampled"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    selected_packet, initial = algo08_position.selected_packet, v5_core.initial_selection
    detail, final_owners = {}, {}

    def evidence(*args):
        packet = selected_packet(*args)
        for arm, rows in packet["rows"].items():
            final_owners[arm] = {r["observation_id"]: int(r["norad"]) for r in rows}
            if len(final_owners[arm]) != len(rows):
                raise ValueError("Duplicate ownership in the selected evidence packet")
        return packet

    def select(scan):
        detail.clear()
        start = process_time()
        if args.mode == "sampled":
            answer, branches = algo08_sampled_initial.select(scan, detail)
        else:
            answer, branches = initial(scan)
        detail["initial_cpu_s"] = process_time() - start
        selected = answer["choices"][answer["selected_hypothesis"]]
        detail.update(branch_count=branches, full_catalogue_size=len(scan.norads),
                      full_original_curved_tracks=len(scan.curved),
                      selected_signature=discovery.signature(selected["node"]),
                      selected_accepted_points=selected["arms"]["c0"]["metrics"]["accepted_points"])
        return answer, branches

    def declare_selection(infer, *args, **kwargs):
        return infer(*args, **kwargs, select_initial=select)

    # Pass the alternative selection explicitly so it can call the original
    # full-data selector when appropriate without entering the wrapper again.
    with (
        patch.object(v5_core, "infer", partial(declare_selection, v5_core.infer)),
        patch.object(algo08_position, "selected_packet", evidence),
    ):
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer)
    result.update(mode=args.mode, native_sha256=args.native_sha256, region=offer.document(),
                  initial=detail, owners=final_owners)
    print(json.dumps(result, default=_json_value, allow_nan=False))


if __name__ == "__main__":
    main()
