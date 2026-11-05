"""External frozen predictive annotation with explicit inputs and captured writes."""

import argparse
import ast
import hashlib
import inspect
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from algo07v3_inventory_oracle import original_inventory
from check_algo07v3_scan_likelihood import fingerprint


def reference_annotation(module, context, inventory, target):
    """Original production run body; replace IO only, retaining scientific branches."""
    tree = ast.parse(inspect.getsource(module.run))

    class NoIO(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call):
                function = node.value.func
                if (isinstance(function, ast.Name) and function.id == "print") or (
                    isinstance(function, ast.Attribute) and function.attr == "mkdir"
                ):
                    return None
            return self.generic_visit(node)

    records = {}
    inv = dict(inventory, job=dict(label="SCAN"))

    def capture(path, value):
        records[path.name] = deepcopy(value)

    namespace = dict(
        module.run.__globals__, read=lambda _: inv, context=lambda _: context, write=capture
    )
    exec(
        compile(
            ast.fix_missing_locations(NoIO().visit(tree)), inspect.getsourcefile(module), "exec"
        ),
        namespace,
    )
    args = SimpleNamespace(
        inventory=None,
        output=Path("/explicit-inputs"),
        track=target["track_id"],
        inactive_fragment=target["inactive_fragment"],
        predictive_member=True,
        distinct_partitions=True,
        shifted_block_origin=True,
        folds=3,
        candidates=12,
        phase_step=0.1,
        uncalibrated_phase_mixture=True,
    )
    namespace[module.run.__name__](args)
    protocol = {k: v for k, v in records["protocol.json"].items() if k != "job"}
    result = {k: v for k, v in records["result.json"].items() if k not in ("job", "seconds")}
    nominations = {
        int(k.removeprefix("nominations-").removesuffix(".json")): v
        for k, v in records.items()
        if k.startswith("nominations-")
    }
    attempts = {
        int(k.removeprefix("seed-").removesuffix(".json")): v
        for k, v in records.items()
        if k.startswith("seed-")
    }
    return dict(protocol=protocol, nominations=nominations, attempts=attempts, result=result)


def run(args):
    sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
    import annotate_predictive_only as original
    import inventory_all_large_tracks
    from algo03_shadow_worker import select_targets
    from benchmark_graph_covariance import baseline_pair, load_case

    started = time.monotonic()
    context = load_case(args.source.parent, args.source.name)
    pair = baseline_pair(context)
    observations = json.loads((args.source / "observations.json").read_bytes())
    inv = original_inventory(
        inventory_all_large_tracks, context["scan"].tracks, observations, pair, args.scan_identities
    )
    target = select_targets(inv)[0][args.target_rank]
    result = reference_annotation(original, context, inv, target)
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    modules = {
        n: binding(m.__file__)
        for n, m in sys.modules.items()
        if getattr(m, "__file__", None)
        and (
            str(m.__file__).startswith(str(args.runtime))
            or n in ("check_algo07v3_scan_likelihood", "algo07v3_inventory_oracle")
        )
    }
    inputs = list(args.source.glob("*")) + list(
        (args.source.parent / "causal_prior" / args.source.name).glob("*")
    )
    inputs += [args.source.parent / "family_cavity" / "position" / (args.source.name + ".json")]
    receipt = dict(
        seconds=time.monotonic() - started,
        source=str(args.source),
        output=binding(args.output),
        modules=modules,
        tool=binding(__file__),
        inputs=[binding(p) for p in inputs if p.is_file()],
        scan_identities=args.scan_identities,
        target_rank=args.target_rank,
        track_id=target["track_id"],
        result_status=result["result"]["annotation"]["status"],
        excluded_fields=["protocol.job", "result.job", "result.seconds"],
    )
    args.output.with_suffix(".receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps({k: receipt[k] for k in ("seconds", "track_id", "result_status", "output")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scan-identities", nargs="+", required=True)
    parser.add_argument("--target-rank", type=int, default=0)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Annotation output already exists")
    run(args)
