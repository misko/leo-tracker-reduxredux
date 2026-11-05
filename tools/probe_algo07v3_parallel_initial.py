"""External experiment: execute independent initial-search c arms concurrently.

No runtime source is changed. The original arm body is extracted with AST,
retaining statement order and arithmetic. Each arm runs in its own forked
process; the parent consumes results in the original c0/fitted-c order. This
Linux-only benchmark does not establish production cancellation behavior.
"""

import argparse
import ast
import copy
import hashlib
import inspect
import json
import multiprocessing
import os
import time
from pathlib import Path

_TASK = None
_ARM_FUNCTION = None
_CPUS = None
_PAIR_EVENTS = []
ARMS = ("c0", "fitted_c")


def transformed_function(module, pair):
    source = inspect.getsource(module.initial_search)
    tree = ast.parse(source)
    loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "arm"
    ]
    if len(loops) != 2 or any(ast.literal_eval(node.iter) != ARMS for node in loops):
        raise ValueError("Expected ordered initial and zero-control c-arm loops")
    # ast.walk visits the top-level zero-control loop before the nested branch
    # loop. Select by its output; leave zero-control fitting serial and unchanged.
    matches = [node for node in loops if ast.unparse(node.body[-1]).startswith("pair[arm] =")]
    if len(matches) != 1:
        raise ValueError("Expected one branch result loop")
    loop = matches[0]
    assignment = loop.body[-1]
    if (
        not isinstance(assignment, ast.Assign)
        or len(assignment.targets) != 1
        or ast.unparse(assignment.targets[0]) != "pair[arm]"
        or loop.orelse
    ):
        raise ValueError("Unexpected arm result or loop control flow")
    helper = ast.parse("def _arm_result(scan, sigma, node, arm, rounds, iterations): pass").body[0]
    helper.body = copy.deepcopy(loop.body[:-1]) + [ast.Return(copy.deepcopy(assignment.value))]

    class Replace(ast.NodeTransformer):
        def visit_For(self, node):
            if node is loop:
                return ast.parse("pair = _pair(scan, sigma, node, rounds, iterations)").body[0]
            return self.generic_visit(node)

    tree = ast.fix_missing_locations(Replace().visit(tree))
    helper_tree = ast.fix_missing_locations(ast.Module(body=[helper], type_ignores=[]))
    scope = dict(vars(module), _pair=pair)
    exec(compile(helper_tree, "<extracted-initial-arm>", "exec"), scope)
    exec(compile(tree, "<parallel-initial-search>", "exec"), scope)
    return scope["initial_search"], scope["_arm_result"], source, ast.unparse(tree)


def _work(arm):
    os.sched_setaffinity(0, {_CPUS[ARMS.index(arm)]})
    scan, sigma, node, rounds, iterations = _TASK
    began, cpu_began = time.perf_counter(), time.process_time()
    result = _ARM_FUNCTION(scan, sigma, node, arm, rounds, iterations)
    return result, dict(
        arm=arm,
        pid=os.getpid(),
        cpu=list(os.sched_getaffinity(0)),
        seconds=time.perf_counter() - began,
        cpu_seconds=time.process_time() - cpu_began,
    )


def parallel_pair(scan, sigma, node, rounds, iterations):
    global _TASK
    if _TASK is not None:
        raise RuntimeError("Nested/concurrent parent benchmark invocation is unsupported")
    _TASK = (scan, sigma, node, rounds, iterations)
    began = time.perf_counter()
    try:
        with multiprocessing.get_context("fork").Pool(2) as pool:
            rows = pool.map(_work, ARMS)
        _PAIR_EVENTS.append(
            dict(seconds=time.perf_counter() - began, workers=[row[1] for row in rows])
        )
        return dict(zip(ARMS, [row[0] for row in rows], strict=True))
    finally:
        _TASK = None


def run(args):
    global _ARM_FUNCTION, _CPUS
    from check_algo07v3_scan_likelihood import fingerprint

    from leo.analysis.localization_v3 import initial_search as module
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application import localization_v3 as application
    from leo.application.localization_v3_engine import _prepared_values
    from leo.operations.tle_archive import TleArchiveReader

    if args.output.exists():
        raise ValueError("Fresh output receipt required")
    affinity = os.sched_getaffinity(0)
    if len(set(args.cpus)) != 2 or not set(args.cpus) <= affinity:
        raise ValueError("Two distinct available CPUs required")
    _CPUS = args.cpus
    manifest_path = args.bundle / "input-bindings.json"
    manifest = json.loads(manifest_path.read_bytes())
    for name, expected in manifest["files"].items():
        path = (args.bundle / name).resolve()
        if not path.is_relative_to(args.bundle.resolve()):
            raise ValueError("Unexpected bundle path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Input bundle changed: " + name)
    candidate, _ARM_FUNCTION, source, candidate_source = transformed_function(module, parallel_pair)
    original = application.initial_search
    os.sched_setaffinity(0, {args.cpus[0]})
    rows, expected = [], None
    try:
        prepared = _prepared_values(
            application.prepare_native_scan(
                json.loads((args.bundle / "native.json").read_bytes()),
                TleArchiveReader(args.bundle / "tle"),
                TrackConfig(**json.loads((args.bundle / "config.json").read_bytes())["config"]),
                screen_latitude_deg=37.5,
                screen_longitude_deg=-122.0,
            )
        )
        for side in ("serial", "parallel", "parallel", "serial"):
            application.initial_search = original if side == "serial" else candidate
            notices = []
            _PAIR_EVENTS.clear()
            began = time.perf_counter()
            value = application.fit_initial_position(
                prepared, SearchRegion((37.906, -122.545)), on_branch=notices.append
            )
            seconds = time.perf_counter() - began
            snapshot = dict(result=fingerprint(value), notices=fingerprint(notices))
            if expected is None:
                expected = snapshot
            exact = snapshot == expected
            row = dict(
                side=side,
                seconds=seconds,
                exact=exact,
                snapshot=snapshot,
                pairs=copy.deepcopy(_PAIR_EVENTS),
                load_average=os.getloadavg(),
            )
            rows.append(row)
            print(json.dumps({k: row[k] for k in ("side", "seconds", "exact")}), flush=True)
            if not exact:
                break
    finally:
        application.initial_search = original
        os.sched_setaffinity(0, affinity)
    receipt = dict(
        complete=len(rows) == 4,
        exact=bool(rows) and all(row["exact"] for row in rows),
        rows=rows,
        scope="Full initial-search stage only; original budgets and both calibration arms",
        cpu_assignment=dict(parent=args.cpus[0], c0=args.cpus[0], fitted_c=args.cpus[1]),
        input_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        candidate_source_sha256=hashlib.sha256(candidate_source.encode()).hexdigest(),
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        enabled_in_runtime=False,
        qualified_pipeline_speedup=None,
    )
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    if not receipt["complete"] or not receipt["exact"]:
        raise SystemExit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cpus", required=True, nargs=2, type=int)
    run(parser.parse_args())
