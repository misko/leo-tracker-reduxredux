"""Measure CPython cyclic collection on a verified saved ALGO08 solve."""

import argparse
import gc
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import sys
from time import perf_counter_ns, process_time_ns

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools.pipeline_eval.variants.algo08_gc_audit import measure_collector
from tools.pipeline_eval.variants.algo08_recovery_reuse import stable_recovery


def rss_kib():
    with open("/proc/self/status") as status:
        return next(int(line.split()[1]) for line in status if line.startswith("VmRSS:"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--defer-preparation", action="store_true")
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    native, archive = json.loads(raw), TleArchiveReader(args.archive)
    with stable_recovery(), measure_collector(defer_preparation=args.defer_preparation) as audit:
        parameters = dict(version=sys.version, enabled=gc.isenabled(),
                          thresholds=gc.get_threshold(), debug=gc.get_debug())
        state = dict(start_rss_kib=rss_kib(), start_garbage=len(gc.garbage))
        wall, cpu = perf_counter_ns(), process_time_ns()
        result = measure("combined", native, archive, args.assets, region)
        state.update(pre_close_rss_kib=rss_kib(), pre_close_garbage=len(gc.garbage))
        with audit.scope("closing_collection"):
            gc.collect(2)
        inclusive = dict(cpu_s=(process_time_ns() - cpu) / 1e9,
                         wall_s=(perf_counter_ns() - wall) / 1e9)
        state.update(
            closed_rss_kib=rss_kib(), closed_garbage=len(gc.garbage),
            closed_tracked=len(gc.get_objects()), peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
            closed_enabled=gc.isenabled(), closed_thresholds=gc.get_threshold(),
        )
    result.update(
        mode="defer" if args.defer_preparation else "control", native_sha256=args.native_sha256,
        region=region.document(), inclusive=inclusive, gc_parameters=parameters, gc_state=state,
        gc_collections=audit.collections, gc_phases=audit.phases,
    )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
