"""External exact-call experiment: skip Gaussian results overwritten by hierarchy.

NormalPosition and DiscoveryPosition overwrite every Gaussian posterior field.
Their geometry-only parent path keeps input validation. Compare every returned
field before accepting any candidate calculation; no runtime source is changed.
"""

import argparse
import hashlib
import inspect
import json
import runpy
import sys
import textwrap
import time
from pathlib import Path

import algo07v3_presolver_discovery_likelihood_oracle as discovery_reference
import algo07v3_presolver_position_oracle as normal_reference
from probe_algo07v3_assembly import exact_result

from leo.analysis.localization_v3.discovery_likelihood import DiscoveryPosition
from leo.analysis.localization_v3.position import NormalPosition


def candidate_function(cls):
    original = {
        NormalPosition: normal_reference.NormalPosition.calculate,
        DiscoveryPosition: discovery_reference.DiscoveryPosition.calculate,
    }[cls]
    source = textwrap.dedent(inspect.getsource(original))
    needle = "JointMarginal.calculate(self, x)"
    if source.count(needle) != 1:
        raise ValueError("Review changed position calculation before probing")
    candidate = source.replace(needle, "JointMarginal.calculate(self, x, geometry_only=True)")
    namespace = dict(original.__globals__)
    exec(compile(candidate, "<skip-overwritten-gaussian>", "exec"), namespace)
    return original, namespace["calculate"], source, candidate


class CalculationMismatch(BaseException):
    """An exactness failure must not become a rejected scientific hypothesis."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("engine_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("Fresh receipt required")
    forwarded = args.engine_args
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        parser.error("Engine arguments required after --")
    records, originals = {}, {}

    def make_probe(cls):
        original, candidate, source, code = candidate_function(cls)
        originals[cls] = cls.calculate
        row = dict(calls=0, seconds=dict(reference=0.0, candidate=0.0), failures=[],
                   reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
                   candidate_sha256=hashlib.sha256(code.encode()).hexdigest())
        records[cls.__name__] = row

        def calculate(self, x):
            order = ("reference", "candidate") if row["calls"] % 2 == 0 else (
                "candidate", "reference")
            functions = dict(reference=original, candidate=candidate)
            values = {}
            for side in order:
                began = time.perf_counter()
                values[side] = functions[side](self, x)
                row["seconds"][side] += time.perf_counter() - began
            row["calls"] += 1
            try:
                exact_result(values["reference"], values["candidate"])
            except ValueError as error:
                row["failures"].append(dict(call=row["calls"], reason=str(error)))
                raise CalculationMismatch(str(error)) from error
            return values["candidate"]

        cls.calculate = calculate

    for cls in (NormalPosition, DiscoveryPosition):
        make_probe(cls)
    tool = Path(__file__).with_name("check_algo07v3_engine.py")
    old_argv, began, complete = sys.argv, time.perf_counter(), False
    sys.argv = [str(tool), *forwarded]
    try:
        runpy.run_path(str(tool), run_name="__main__")
        complete = True
    finally:
        sys.argv = old_argv
        for cls, original in originals.items():
            cls.calculate = original
        result = dict(
            complete=complete, calculations=records,
            exact=complete and all(r["calls"] > 0 and not r["failures"] for r in records.values()),
            process_seconds=time.perf_counter() - began,
            tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            engine_tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
            arguments=forwarded, enabled_in_runtime=False, qualified_speedup=None,
        )
        with args.receipt.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
