"""Measure exact hierarchical-input repetition without skipping any numerical work.

Run the native/prepared qualification CLI under observation. Report bounded LRU
hit opportunities and time actually spent recomputing those calls. This is an
upper bound on removable compute, not a cache implementation or speed claim.
"""

import argparse
import hashlib
import inspect
import json
import runpy
import sys
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np


class RepeatProbe:
    def __init__(self, function, capacities=(8, 32, 128, 512, 2048), clock=time.perf_counter):
        self.function, self.signature, self.clock = function, inspect.signature(function), clock
        self.caches = {n: OrderedDict() for n in capacities}
        self.rows = {
            n: dict(hits=0, repeated_compute_seconds=0.0) for n in capacities
        }
        self.calls = 0
        self.keys = set()
        self.compute_seconds = self.observation_seconds = 0.0
        self.callers = {}

    def key(self, args, kwargs):
        bound = self.signature.bind(*args, **kwargs)
        bound.apply_defaults()
        h = hashlib.sha256()
        for name, value in bound.arguments.items():
            # Length-delimited metadata prevents shape/dtype/value ambiguity.
            if isinstance(value, (np.ndarray, list, tuple)):
                a = np.asarray(value)
                if a.dtype.hasobject:
                    raise ValueError("Numerical input probe does not support object arrays")
                meta = [name, "array", a.dtype.str, list(a.shape)]
                raw = a.tobytes(order="C")
            else:
                meta = [name, type(value).__name__]
                raw = json.dumps(value, allow_nan=False).encode()
            header = json.dumps(meta, separators=(",", ":")).encode()
            h.update(len(header).to_bytes(8, "little"))
            h.update(header)
            h.update(len(raw).to_bytes(8, "little"))
            h.update(raw)
        return h.digest()

    def __call__(self, *args, **kwargs):
        started = self.clock()
        key = self.key(args, kwargs)
        hits = {n: key in cache for n, cache in self.caches.items()}
        caller = sys._getframe(1).f_globals.get("__name__", "unknown")
        before = self.clock()
        value = self.function(*args, **kwargs)
        after = self.clock()
        elapsed = after - before
        self.calls += 1
        self.keys.add(key)
        self.compute_seconds += elapsed
        row = self.callers.setdefault(caller, dict(calls=0, compute_seconds=0.0))
        row["calls"] += 1
        row["compute_seconds"] += elapsed
        for n, cache in self.caches.items():
            if hits[n]:
                self.rows[n]["hits"] += 1
                self.rows[n]["repeated_compute_seconds"] += elapsed
                cache.move_to_end(key)
            else:
                cache[key] = None
                if len(cache) > n:
                    cache.popitem(last=False)
        self.observation_seconds += before - started + self.clock() - after
        return value

    def report(self):
        return dict(
            calls=self.calls,
            unique_input_digests=len(self.keys),
            compute_seconds=self.compute_seconds,
            observation_seconds=self.observation_seconds,
            callers=self.callers,
            lru_capacities=self.rows,
            numerical_calls_skipped=0,
            interpretation="Potential repeated compute only; excludes cache copy and lookup costs",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-output", type=Path, required=True)
    parser.add_argument("engine_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.profile_output.exists():
        parser.error("Fresh profile output required")
    forwarded = args.engine_args
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        parser.error("Qualification arguments required after --")
    from leo.analysis.localization_v3 import hierarchical

    probe = RepeatProbe(hierarchical.hierarchical_bound)
    hierarchical.hierarchical_bound = probe
    tool = Path(__file__).with_name("check_algo07v3_engine.py")
    original = sys.argv
    sys.argv = [str(tool), *forwarded]
    began = time.perf_counter()
    completed = False
    try:
        runpy.run_path(str(tool), run_name="__main__")
        completed = True
    finally:
        sys.argv = original
        hierarchical.hierarchical_bound = probe.function
        report = dict(
            probe.report(),
            qualification_completed=completed,
            process_seconds=time.perf_counter() - began,
            arguments=forwarded,
            probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            engine_tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
        )
        with args.profile_output.open("x") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")


if __name__ == "__main__":
    main()
