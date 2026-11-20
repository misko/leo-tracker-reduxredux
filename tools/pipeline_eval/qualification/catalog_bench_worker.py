"""Bind the frozen checksum inside the isolated installed receiver process."""

import ast
import json
import runpy
import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

CHECKSUM = "element_line_checksum"
RELATIVE = "leo/sky/propagation.py"


def digest(data):
    return sha256(data).hexdigest()


def definitions(tree):
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = node
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                result[target.id] = node
    return result


def freeze_checksum(installed, source, propagation):
    stock = definitions(ast.parse(installed))
    tree = ast.parse(source)
    candidate = definitions(tree)
    for name in ("_CHECKSUM_COLUMN", "ELEMENT_LINE_LENGTH", "_validate_element_line"):
        if ast.dump(stock[name]) != ast.dump(candidate[name]):
            raise ValueError(f"line validation source changed at {name}")
    function = candidate[CHECKSUM]
    names = {n.id for n in ast.walk(function) if isinstance(n, ast.Name)}
    support = names & candidate.keys() - {"_CHECKSUM_COLUMN", CHECKSUM}
    if len(support) != 1 or not all(
        name.startswith("_CHECKSUM") and isinstance(candidate[name], ast.Assign) for name in support
    ):
        raise ValueError(f"unexpected checksum globals {sorted(support)}")
    futures = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "__future__"]
    nodes = [*futures, *(candidate[name] for name in sorted(support)), function]
    compiled = ast.Module(body=nodes, type_ignores=[])
    env = dict(__name__=propagation.__name__, _CHECKSUM_COLUMN=propagation._CHECKSUM_COLUMN)
    exec(compile(compiled, "frozen-production-propagation.py", "exec"), env)
    return env[CHECKSUM], dict(
        checksum_ast_sha256=digest(ast.dump(compiled).encode()),
        installed_checksum_ast_sha256=digest(ast.dump(stock[CHECKSUM]).encode()),
        line_validation_ast_sha256=digest(ast.dump(stock["_validate_element_line"]).encode()),
        parser_source_equal=ast.dump(stock["parse_element_sets"])
        == ast.dump(candidate["parse_element_sets"]),
        support=sorted(support),
    )


def code(work, lock, propagation):
    installed = (Path(lock["receiver"]) / RELATIVE).read_bytes()
    source = (work / "production-propagation.py").read_bytes()
    if digest(installed) != lock["installed_files"][RELATIVE]:
        raise ValueError("installed checksum source changed")
    if digest(source) != lock["production_sha256"].removeprefix("sha256:"):
        raise ValueError("frozen production source changed")
    return freeze_checksum(installed, source, propagation)


def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, allow_nan=False, sort_keys=True) + "\n")
    tmp.replace(path)


def position(folder, request, work, lock, entry):
    from leo.application import localization_v3
    from leo.sky import propagation
    from tools.pipeline_eval.variants import v5_direct_cavity

    plan = json.loads((folder / "plan.json").read_bytes())
    branch = plan["branch"]
    candidate, provenance = code(work, lock, propagation)
    checksum = {"installed": propagation.element_line_checksum, "frozen_checksum": candidate}[
        branch
    ]
    fingerprint = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "variants/track_preparation.py")
    )["fingerprint"]
    calls, clocks = [0, 0], {}

    def counted(line):
        calls[0] += 1
        if type(line) is not str or not line.isascii():
            prefix = line[: propagation._CHECKSUM_COLUMN]
            calls[1] += type(prefix) is not str or not prefix.isascii()
        return checksum(line)

    def measure(name, operation, *, after=None):
        def run(*args, **kwargs):
            wall, cpu, count = perf_counter(), process_time(), calls[0]
            result = operation(*args, **kwargs)
            clocks[name] = dict(
                cpu_s=process_time() - cpu,
                wall_s=perf_counter() - wall,
                checksum_calls=calls[0] - count,
            )
            if after is not None:
                after(result)
            return result

        return run

    def preparation(data):
        tracks = data["tracks"]
        science = dict(
            status=data["status"],
            ordered_tracks_sha256=fingerprint(tracks),
            observations=len(tracks["observations"]),
            tracks=len(tracks["tracks"]),
            assigned_points=tracks["graph_points"],
            curved_tracks=len(tracks["curved_indices"]),
        )
        if data["status"] == "inputs_prepared":
            science["causal_sha256"] = fingerprint(
                [
                    data["sky"]["metadata"],
                    data["noise"],
                    data["phase_history"],
                    data["phase_forecast"],
                ]
            )
        write_json(
            folder / "preparation.json",
            dict(
                provenance=provenance,
                branch=branch,
                science=science,
                checksum_calls=calls[0],
                fallback_calls=calls[1],
                clocks=clocks,
            ),
        )

    entry["validate_region"](request["tile"], request["screen_center"], request["width_km"])
    with ExitStack() as stack:
        stack.enter_context(patch.object(propagation, CHECKSUM, counted))
        for key, label in (
            ("prepare_tracks", "tracks"),
            ("prepare_initial_sky", "initial_sky"),
            ("prepare_phase_history", "phase_history"),
        ):
            stack.enter_context(
                patch.object(localization_v3, key, measure(label, getattr(localization_v3, key)))
            )
        stack.enter_context(
            patch.object(
                localization_v3,
                "prepare_native_scan",
                measure(
                    "native_preparation", localization_v3.prepare_native_scan, after=preparation
                ),
            )
        )
        wall, cpu = perf_counter(), process_time()
        result = v5_direct_cavity.run(**request)
    entry["verify_project_modules"](Path(lock["receiver"]))
    write_json(
        folder / "numerical.json",
        dict(
            numerical=result,
            position_cpu_s=process_time() - cpu,
            position_wall_s=perf_counter() - wall,
            checksum_calls=calls[0],
            fallback_calls=calls[1],
        ),
    )


def main():
    action, argument = sys.argv[1:]
    folder = Path(argument).resolve()
    if action != "position":
        raise ValueError("unexpected isolated catalog benchmark action")
    work = folder.parents[1]
    lock = json.loads((work / "source-lock.json").read_bytes())
    root = Path(lock["receiver"])
    entry = runpy.run_path(str(root / "__main__.py"))
    entry["activate"](root)
    position(folder, json.load(sys.stdin), work, lock, entry)


if __name__ == "__main__":
    main()
