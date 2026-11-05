"""Frozen signed-context numerical body with explicit inputs, external audit only."""

import ast
import inspect


def reference_signed_context(
    scan,
    original_result,
    family_result,
    raw,
    forecast,
    observations,
    *,
    case,
    history_sha256,
    signed=True,
):
    import fast_graph_engine as original

    function = ast.parse(inspect.getsource(original.context)).body[0]
    function.name = "numerical_context"
    names = (
        "scan",
        "original",
        "old",
        "raw",
        "forecast",
        "observations",
        "case",
        "history_sha256",
        "signed",
    )
    function.args = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=n) for n in names],
        kwonlyargs=[],
        kw_defaults=[],
        defaults=[],
    )

    class ExplicitInputs(ast.NodeTransformer):
        def visit_Assign(self, node):
            targets = {
                n.id
                for t in node.targets
                for n in ast.walk(t)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
            }
            if targets.intersection(
                ("root", "old", "original", "scan", "history", "forecast_path", "raw", "forecast")
            ):
                return None
            return self.generic_visit(node)

        def visit_Expr(self, node):
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "bind_run_directory"
            ):
                return None
            return self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == "sha":
                return ast.Name(id="history_sha256", ctx=ast.Load())
            if isinstance(node.func, ast.Name) and node.func.id == "read":
                raise ValueError("Unexpected retained old storage read")
            if isinstance(node.func, ast.Name) and node.func.id == "dict":
                node.keywords = [kw for kw in node.keywords if kw.arg != "binding"]
                for kw in node.keywords:
                    if kw.arg == "observations":
                        kw.value = ast.Name(id="observations", ctx=ast.Load())
            return self.generic_visit(node)

    namespace = dict(original.context.__globals__)
    tree = ast.Module(body=[ExplicitInputs().visit(function)], type_ignores=[])
    exec(
        compile(ast.fix_missing_locations(tree), inspect.getsourcefile(original), "exec"), namespace
    )
    return namespace["numerical_context"](
        scan,
        original_result,
        family_result,
        raw,
        forecast,
        observations,
        case,
        history_sha256,
        signed,
    )


def run(args):
    """Reconstruct the full original signed context from an explicit export."""
    import hashlib
    import json
    import sys
    import time
    from pathlib import Path

    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Fresh signed oracle outputs required")
    sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
    from check_algo07v3_position import signed_snapshot
    from check_algo07v3_scan_likelihood import fingerprint
    from evaluate_ds23_phase_refreshed import FreshScan

    inputs = {}

    def read(path, *, raw=False):
        data = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(data).hexdigest()
        return data if raw else json.loads(data)

    began = time.monotonic()
    prior = args.source.parent / "causal_prior" / args.source.name
    for directory in (args.source, prior):
        for path in directory.iterdir():
            if path.is_file():
                read(path, raw=True)
    scan = FreshScan(args.source, noise_mode="radio")
    scan.previous_tle_path = prior / "previous.tle"
    scan.receipt = read(prior / "receipt.json")
    history = args.source.parent / "causal_phase_history" / (args.source.name + ".json")
    raw = read(history)
    forecast = read(history.with_name(args.source.name + "_forecast.json"))
    result = reference_signed_context(
        scan,
        read(args.source / "result.json"),
        read(args.source / "algo02_result.json"),
        raw,
        forecast,
        read(args.source / "observations.json"),
        case=args.source.name,
        history_sha256=inputs[str(history)],
    )
    snapshot = fingerprint(signed_snapshot(result))
    with args.output.open("x") as stream:
        json.dump(snapshot, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    for path, digest in inputs.items():
        if binding(path)["sha256"] != digest:
            raise ValueError("Reference input changed: " + path)
    modules = {
        n: binding(m.__file__)
        for n, m in sys.modules.items()
        if getattr(m, "__file__", None)
        and (
            str(m.__file__).startswith(str(args.runtime))
            or n in ("check_algo07v3_position", "check_algo07v3_scan_likelihood")
        )
    }
    receipt = dict(
        seconds=time.monotonic() - began,
        source=str(args.source),
        output=binding(args.output),
        tool=binding(__file__),
        modules=modules,
        inputs=[dict(path=p, sha256=d) for p, d in sorted(inputs.items())],
        scope="Complete signed numerical context and likelihood snapshot; explicit frozen inputs",
    )
    with args.output.with_suffix(".receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(seconds=receipt["seconds"], output=receipt["output"])))


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
