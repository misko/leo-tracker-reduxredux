"""Compare every native likelihood call to the external scatter prototype.

Both implementations execute on each input. The candidate's exact result is
returned to the engine; a single differing field aborts qualification. Timings
are interleaved component observations, not full-engine speedup measurements.
"""

import argparse
import hashlib
import json
import runpy
import sys
import time
from pathlib import Path

import numpy as np


def exact_result(expected, actual):
    if expected.keys() != actual.keys():
        raise ValueError("Likelihood output fields changed")
    for name in expected:
        a, b = np.asarray(expected[name]), np.asarray(actual[name])
        if a.dtype != b.dtype or a.shape != b.shape or a.tobytes() != b.tobytes():
            raise ValueError("Likelihood output changed: " + name)


class AssemblyProbe:
    def __init__(self, reference, candidate, clock=time.perf_counter):
        self.reference, self.candidate, self.clock = reference, candidate, clock
        self.calls = 0
        self.shapes = {}
        self.seconds = dict(reference=0.0, candidate=0.0)
        self.failures = []

    def __call__(self, *args, **kwargs):
        # Alternate ordering to avoid always rewarding one side with warmer data.
        order = ("reference", "candidate") if self.calls % 2 == 0 else ("candidate", "reference")
        values = {}
        for side in order:
            began = self.clock()
            values[side] = getattr(self, side)(*args, **kwargs)
            self.seconds[side] += self.clock() - began
        self.calls += 1
        shape = str(tuple(np.asarray(args[1]).shape))
        self.shapes[shape] = self.shapes.get(shape, 0) + 1
        try:
            exact_result(values["reference"], values["candidate"])
        except ValueError as error:
            self.failures.append(dict(call=self.calls, shape=shape, error=str(error)))
            raise
        return values["candidate"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("engine_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("Fresh output receipt required")
    forwarded = args.engine_args
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        parser.error("Native qualification arguments required after --")
    from leo.analysis.localization_v3 import hierarchical

    experiment = (
        Path(__file__).resolve().parents[1] / "reports/2026_11_05_algo07v3_pair/probe_assembly.py"
    )
    candidate, old_source, new_source = runpy.run_path(str(experiment))["candidate_function"]()
    probe = AssemblyProbe(hierarchical.hierarchical_bound, candidate)
    hierarchical.hierarchical_bound = probe
    tool = Path(__file__).with_name("check_algo07v3_engine.py")
    original_argv = sys.argv
    sys.argv = [str(tool), *forwarded]
    began = time.perf_counter()
    complete = False
    try:
        runpy.run_path(str(tool), run_name="__main__")
        complete = True
    finally:
        sys.argv = original_argv
        hierarchical.hierarchical_bound = probe.reference
        result = dict(
            complete=complete,
            calls=probe.calls,
            failures=probe.failures,
            exact=complete and probe.calls > 0 and not probe.failures,
            shapes=probe.shapes,
            component_seconds=probe.seconds,
            process_seconds=time.perf_counter() - began,
            reference_sha256=hashlib.sha256(old_source.encode()).hexdigest(),
            candidate_sha256=hashlib.sha256(new_source.encode()).hexdigest(),
            tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            engine_tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
            arguments=forwarded,
            enabled_in_runtime=False,
            qualified_speedup=None,
        )
        with args.receipt.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
