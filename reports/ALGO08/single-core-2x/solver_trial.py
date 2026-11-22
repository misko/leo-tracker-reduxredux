"""Compare ALGO08v2 and experimental solver ports on saved, verified detections."""

import argparse
from contextlib import ExitStack
from functools import partial
import hashlib
import json
import resource
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from leo.analysis.localization_v3 import conservative_recovery
from tools.pipeline_eval.variants import algo08_causal_reuse, algo08_salvage_statistics


def measure(mode, native, archive, assets, region):
    preparation = algo08_position.prepare_native_scan
    stats, stages, trims = {}, {}, []
    if mode in ("causal-reuse", "combined"):
        preparation = partial(algo08_causal_reuse.prepare, preparation, statistics=stats)

    def timed(operation, *args, **kwargs):
        start_cpu, start_wall = process_time(), perf_counter()
        try:
            return operation(*args, **kwargs)
        finally:
            row = stages.setdefault(operation.__name__, dict(cpu_s=0, wall_s=0, calls=0))
            row["cpu_s"] += process_time() - start_cpu
            row["wall_s"] += perf_counter() - start_wall
            row["calls"] += 1

    def prepare(*args, **kwargs):
        return timed(prepare_scan, *args, **kwargs)

    def prepare_scan(*args, **kwargs):
        return preparation(*args, **kwargs)

    with ExitStack() as stack:
        counters, shortlists = {}, []
        if mode in ("salvage-statistics", "combined"):
            counters, shortlists = stack.enter_context(algo08_salvage_statistics.salvage_statistics())
        stock_salvage = conservative_recovery.salvage

        def salvage(*args, **kwargs):
            return stock_salvage(*args, **kwargs)

        def trace_salvage(*args, **kwargs):
            result = timed(salvage, *args, **kwargs)
            trims.extend(result[2])
            return result

        stack.enter_context(patch.object(conservative_recovery, "salvage", trace_salvage))
        stack.enter_context(patch.object(algo08_position, "prepare_native_scan", prepare))
        stack.enter_context(patch.object(algo08_position, "selected_packet",
                                         partial(timed, algo08_position.selected_packet)))
        start_cpu, start_wall = process_time(), perf_counter()
        result, packet, policy = algo08_position.solve(native, archive, assets, region)
        cpu, wall = process_time() - start_cpu, perf_counter() - start_wall
    return dict(mode=mode, cpu_s=cpu, wall_s=wall, stages=stages, cache=stats,
                salvage_counters=dict(counters), trims=trims, shortlists=shortlists,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                decision=result, orbit_policy=policy,
                evidence=None if packet is None else {
                    key: packet[key] for key in (
                        "arms", "objective_replay", "position_path", "position_grid"
                    )
                })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("stock", "causal-reuse", "salvage-statistics", "combined"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    receipt = measure(args.mode, json.loads(raw), TleArchiveReader(args.archive), args.assets, region)
    print(json.dumps(dict(receipt, native_sha256=args.native_sha256, region=region.document()),
                     allow_nan=False))


if __name__ == "__main__":
    main()
