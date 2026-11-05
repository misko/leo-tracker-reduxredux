"""External experiment: ordered independent c-arm fits in the family policy.

No runtime source changes. The existing bounded process adapter isolates each
arm. Gating, data removal and curved-to-linear decisions remain sequential.
"""

import argparse
import copy
import hashlib
import inspect
import json
import resource
import runpy
import sys
import time
from pathlib import Path

import algo07v3_prefamily_policy_oracle as policy
from check_algo07v3_scan_likelihood import fingerprint

from leo.operations.localization_v3_parallel import map_initial_arms


def transformed_functions(map_arms):
    source = (inspect.getsource(policy.history_policy) + "\n\n"
              + inspect.getsource(policy.history_fit))
    replacements = {
        """linear = {
        arm: linear_refit(scan, node, keep, powers, means, model, arm, entries) for arm in ARMS
    }""": """linear = dict(zip(ARMS, _map_arms(
        lambda arm: linear_refit(scan, node, keep, powers, means, model, arm, entries),
        ARMS), strict=True))""",
        """pair = {
            arm: refit(scan, node, keep, arm, powers, means, model["multiplier"], model["nu"])
            for arm in ARMS
        }""": """pair = dict(zip(ARMS, _map_arms(
            lambda arm: refit(scan, node, keep, arm, powers, means,
                              model["multiplier"], model["nu"]), ARMS), strict=True))""",
    }
    code = source
    for before, after in replacements.items():
        if code.count(before) != 1:
            raise ValueError("Review changed family policy before parallel probing")
        code = code.replace(before, after)
    namespace = dict(vars(policy), _map_arms=map_arms)
    exec(compile(code, "<parallel-family-arms>", "exec"), namespace)
    return namespace, source, code


class FamilyMismatch(BaseException):
    """An incomplete exactness check must not become a scientific rejection."""


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
    from leo.application import localization_v3 as application
    original = policy.history_policy
    runtime_function = application.history_policy
    rows, pairs = [], []

    def mapper(operation, arms):
        began = time.perf_counter()
        result = map_initial_arms(operation, arms)
        pairs.append(dict(arms=list(arms), seconds=time.perf_counter() - began))
        return result

    namespace, source, code = transformed_functions(mapper)

    def compare(*positional, **keywords):
        outputs, clocks = {}, {}
        functions = dict(reference=original, candidate=namespace["history_policy"])
        order = ("reference", "candidate") if len(rows) % 2 == 0 else ("candidate", "reference")
        # Give each method the same starting cache state; copying is outside the
        # stage clocks. No reference result enters candidate calculation.
        inputs = {side: copy.deepcopy((positional, keywords)) for side in order}
        for side in order:
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            began, cpu_began = time.perf_counter(), time.process_time()
            outputs[side] = functions[side](*inputs[side][0], **inputs[side][1])
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            clocks[side] = dict(seconds=time.perf_counter() - began,
                                parent_cpu_seconds=time.process_time() - cpu_began,
                                children_cpu_seconds=(after.ru_utime + after.ru_stime
                                                      - before.ru_utime - before.ru_stime))
        if fingerprint(outputs["reference"]) != fingerprint(outputs["candidate"]):
            rows.append(dict(exact=False, clocks=clocks, error="Family policy outputs changed"))
            raise FamilyMismatch("Family policy outputs changed")
        rows.append(dict(exact=True, clocks=clocks))
        return outputs["candidate"]

    application.history_policy = compare
    tool = Path(__file__).with_name("check_algo07v3_engine.py")
    old_argv, began, complete = sys.argv, time.perf_counter(), False
    sys.argv = [str(tool), *forwarded]
    try:
        runpy.run_path(str(tool), run_name="__main__")
        complete = True
    finally:
        application.history_policy = runtime_function
        sys.argv = old_argv
        result = dict(complete=complete, exact=complete and bool(rows)
                      and all(r["exact"] for r in rows), comparisons=rows, pairs=pairs,
                      process_seconds=time.perf_counter() - began,
                      reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
                      candidate_sha256=hashlib.sha256(code.encode()).hexdigest(),
                      tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      engine_tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
                      arguments=forwarded, enabled_in_runtime=False, qualified_speedup=None)
        with args.receipt.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
