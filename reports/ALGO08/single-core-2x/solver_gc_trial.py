"""Measure CPython cyclic collection on a verified saved ALGO08 solve."""

import argparse
from contextlib import ExitStack, contextmanager
import gc
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


def rss_kib():
    with open("/proc/self/status") as status:
        return next(int(line.split()[1]) for line in status if line.startswith("VmRSS:"))


@contextmanager
def composed_parser(pin):
    from tools.pipeline_eval.variants import v5_core, v5_direct_cavity
    from tools.pipeline_eval.variants.algo08_causal_table import causal_table
    from tools.pipeline_eval.variants.algo08_cavity_projection import shared_projection
    from tools.pipeline_eval.variants.algo08_dense_discovery import dense_discovery
    from tools.pipeline_eval.variants.algo08_endpoint_readout import measured_readout
    from tools.pipeline_eval.variants.algo08_salvage_bound import stable_pruning
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    library, expected = pin
    contents = Path(library).read_bytes()
    digest = sha256(contents).hexdigest()
    if digest != expected:
        raise ValueError("TLE parser differs from its reviewed build")
    original_rank = v5_core.ranked_initial_nodes

    def shared_rank(scan):
        with dense_discovery(scan, reuse_associations=True):
            return original_rank(scan)

    with TemporaryDirectory() as scratch, ExitStack() as stack:
        pinned_library = Path(scratch) / "_leo_tle_records.so"
        pinned_library.write_bytes(contents)
        records = stack.enter_context(batch_records(pinned_library))
        stack.enter_context(patch.object(v5_core, "ranked_initial_nodes", shared_rank))
        table = stack.enter_context(causal_table(canonical_exports=True, previous_catalogues=True))
        stack.enter_context(shared_projection())
        stack.enter_context(stable_pruning("gate"))
        stack.enter_context(measured_readout(v5_direct_cavity, reuse=True))
        yield dict(tle_sha256=digest, parser=records, table=table)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--defer-preparation", action="store_true")
    parser.add_argument("--composed-tle-parser", nargs=2, metavar=("LIBRARY", "SHA256"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    if args.composed_tle_parser:
        from tools.pipeline_eval.variants.experimental.lean_startup import install

        install()
    from leo.contracts.algo08_region import Algo08Region
    from leo.operations.tle_archive import TleArchiveReader
    from solver_trial import measure
    from tools.pipeline_eval.variants.algo08_gc_audit import measure_collector
    from tools.pipeline_eval.variants.algo08_recovery_reuse import stable_recovery

    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    native, archive = json.loads(raw), TleArchiveReader(args.archive)
    with ExitStack() as stack:
        composition = None
        if args.composed_tle_parser:
            composition = stack.enter_context(composed_parser(args.composed_tle_parser))
        stack.enter_context(stable_recovery())
        audit = stack.enter_context(measure_collector(defer_preparation=args.defer_preparation))
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
    if composition is not None:
        result["composition"] = composition
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
