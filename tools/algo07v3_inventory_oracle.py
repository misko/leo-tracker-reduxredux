"""External frozen ALGO03 recovery-inventory oracle; never an inference import.

Reads the archived cavity decision only on the reference side. The candidate
must derive its own cavity decision from native prepared inputs. Original
inventory arithmetic executes unchanged; only job labels/paths are omitted.
"""

import argparse
import ast
import hashlib
import inspect
import json
import sys
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint


def original_inventory(module, tracks, observations, pair, identities):
    tree = ast.parse(inspect.getsource(module.one)).body[0]
    start = next(
        i
        for i, n in enumerate(tree.body)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "all_ids" for t in n.targets)
    )
    end = next(
        i
        for i, n in enumerate(tree.body)
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "write"
    )
    namespace = dict(
        module.one.__globals__,
        tracks=tracks,
        observations=observations,
        current=pair,
        original=pair,
        job=dict(
            identities=identities, job_id="external-oracle", label="SCAN", aliases=[], scopes=[]
        ),
    )
    exec(
        compile(
            ast.Module(body=tree.body[start:end], type_ignores=[]),
            inspect.getsourcefile(module),
            "exec",
        ),
        namespace,
    )

    def science(rows):
        return [
            {k: v for k, v in row.items() if k not in ("job_id", "label", "aliases", "scopes")}
            for row in rows
        ]

    return dict(
        summary=science(namespace["summary"]),
        tracks=science(namespace["rows"]),
        policy=pair,
        prior_policy=pair,
    )


def run(args):
    sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
    import algo03_inventory
    import inventory_all_large_tracks
    from algo03_shadow_worker import select_targets
    from benchmark_graph_covariance import baseline_pair, load_case
    from debug_fast_graph_unassociated import memberships

    began = time.monotonic()
    context = load_case(args.source.parent, args.source.name)
    pair = baseline_pair(context)
    owners = {
        a: memberships(p, x, context["entries"])[3] for a, (p, x) in context["problems"].items()
    }
    observations = json.loads((args.source / "observations.json").read_bytes())
    inv = original_inventory(
        inventory_all_large_tracks, context["scan"].tracks, observations, pair, args.scan_identities
    )
    selected, eligible = select_targets(inv)
    support = algo03_inventory.publication_support(
        dict(arms=context["saved"]["policy_arms"]), owners
    )
    result = dict(
        inventory=inv,
        publication_support=support,
        owners=owners,
        baseline_objective_replay=context["replay"],
        selected_targets=selected,
        eligible_targets=eligible,
    )
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    modules = {
        n: binding(m.__file__)
        for n, m in sys.modules.items()
        if getattr(m, "__file__", None)
        and (str(m.__file__).startswith(str(args.runtime)) or n == "check_algo07v3_scan_likelihood")
    }
    inputs = list(args.source.glob("*")) + list(
        (args.source.parent / "causal_prior" / args.source.name).glob("*")
    )
    inputs += [args.source.parent / "family_cavity" / "position" / (args.source.name + ".json")]
    receipt = dict(
        seconds=time.monotonic() - began,
        source=str(args.source),
        output=binding(args.output),
        modules=modules,
        tool=binding(__file__),
        inputs=[binding(p) for p in inputs if p.is_file()],
        scan_identities=args.scan_identities,
        eligible_targets=eligible,
        excluded_inventory_metadata=["job_id", "label", "aliases", "scopes"],
    )
    args.output.with_suffix(".receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps({k: receipt[k] for k in ("seconds", "eligible_targets", "output")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scan-identities", nargs="+", required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Oracle output already exists")
    run(args)
