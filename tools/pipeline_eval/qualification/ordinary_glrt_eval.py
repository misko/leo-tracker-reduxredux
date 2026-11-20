"""Qualify the ordinary retained fine-frequency band on new saved-IQ visits."""

import argparse
import gzip
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from leo.analysis.starlink import native_short_window

from ..__main__ import ROOT, encoded, local_output, write
from ..variants import iq_stream
from . import ordinary_front_build, ordinary_front_eval, ordinary_glrt_build
from .full_v5_check import NATIVE_LIBRARY, PRODUCERS, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/deployment/ordinary-glrt"
METHOD = "ordinary_glrt_band"
SCHEDULE = ((9, (13, 17, 23, 29)), (10, (13, 17, 23, 29)))
MODES = ("control", METHOD)
CHUNK_PREFIX = 48 * iq_stream.MIB


def sources():
    paths = (
        Path(__file__),
        Path(ordinary_glrt_build.__file__),
        ordinary_glrt_build.HEADER,
        Path(ordinary_front_eval.__file__),
        Path(ordinary_front_build.__file__),
        Path(iq_stream.__file__),
        REPORT / "PROTOCOL.md",
        NATIVE_LIBRARY,
        ordinary_front_build.ARM_CONTROL / "leo-native-glrt-short-window",
    )
    return {p.name: _sha(p) for p in paths}


def replay(ident, work, arch):
    init = {}
    production = native_short_window.NativeShortWindow

    def construct(path, *args, **kwargs):
        wall, cpu = perf_counter(), process_time()
        context = production(path, *args, **kwargs)
        mode = "control" if path == str(NATIVE_LIBRARY) else METHOD
        init[mode] = dict(wall_s=perf_counter() - wall, cpu_s=process_time() - cpu)
        return context

    bench = ordinary_front_eval.benchmark

    def benchmark(samples, call, index, repeats):
        return bench(samples, call, index, 5 if repeats == 3 else repeats)

    with (
        patch.multiple(
            ordinary_front_eval, METHOD=METHOD, MODES=MODES, SCHEDULE=SCHEDULE, benchmark=benchmark
        ),
        patch.object(native_short_window, "NativeShortWindow", construct),
        patch.object(iq_stream, "MAX_CHUNK_PREFIX", CHUNK_PREFIX),
    ):
        receipt = ordinary_front_eval.replay(ident, work, arch)
    return dict(
        receipt,
        host_context_construction=init,
        build_receipt_sha256=_sha(work / arch / "build-receipt.json"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--arch", choices=("host", "arm"), required=True)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    frozen = sources()
    if (REPORT / "source-lock.json").read_bytes() != encoded(frozen) + b"\n":
        raise ValueError("Ordinary GLRT trial source does not match the pre-score lock")
    receipt = replay(args.case, local_output(args.work), args.arch)
    if sources() != frozen:
        raise ValueError("Ordinary GLRT trial source changed during replay")
    write(REPORT / f"{args.case}-{args.arch}.json.gz", gzip.compress(encoded(receipt), mtime=0))


if __name__ == "__main__":
    main()
