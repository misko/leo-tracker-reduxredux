"""Measure local time-polynomial discovery through full published evidence."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from leo.analysis.localization_v3.discovery import signature
from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_track_moments, v5_core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "moments"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    create, evidence = v5_core.scan_context, algo08_position.selected_packet
    initial, owners = {}, {}

    def timed_context(*values):
        start = process_time()
        if args.mode == "moments":
            scan = algo08_track_moments.prepare_context(create, *values)
        else:
            scan = create(*values)
        if values[-1] == "previous":
            initial["context_cpu_s"] = process_time() - start
        return scan

    def select(scan):
        start = process_time()
        if args.mode == "moments":
            answer, count = algo08_track_moments.select(scan, initial)
        else:
            rank_start = process_time()
            nodes = v5_core.ranked_initial_nodes(scan)
            initial.update(broad_and_exact_cold_rank_cpu_s=process_time() - rank_start,
                           ranked_signatures=[signature(node) for node in nodes])
            fit_start = process_time()
            answer, count = v5_core.fit_initial_nodes(scan, nodes[:3])
            initial["exact_refreshed_fit_cpu_s"] = process_time() - fit_start
        selected = answer["choices"][answer["selected_hypothesis"]]
        initial.update(selection_cpu_s=process_time() - start,
                       selected_signature=signature(selected["node"]), branches=count,
                       accepted_points=selected["arms"]["c0"]["metrics"]["accepted_points"])
        return answer, count

    def selected_packet(*values):
        packet = evidence(*values)
        for arm, rows in packet["rows"].items():
            owners[arm] = {r["observation_id"]: int(r["norad"]) for r in rows}
            if len(owners[arm]) != len(rows):
                raise ValueError("Duplicate observation IDs in the selected evidence packet")
        return packet

    def bind_infer(infer, *values, **options):
        return infer(*values, **options, select_initial=select)

    with (
        patch.object(v5_core, "infer", partial(bind_infer, v5_core.infer)),
        patch.object(v5_core, "scan_context", timed_context),
        patch.object(algo08_position, "selected_packet", selected_packet),
    ):
        result = measure(
            "combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer
        )
    result.update(mode=args.mode, initial=initial, owners=owners,
                  native_sha256=args.native_sha256, region=offer.document())
    print(json.dumps(result, default=_json_value, allow_nan=False))


if __name__ == "__main__":
    main()
