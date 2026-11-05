"""External frozen inclusion/retry oracle, with explicit in-memory IO adapters.

Only operational IO is replaced. The original fit, audit and acceptance bodies
execute in the frozen runtime; no candidate numerical code is imported.
"""

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

from algo07v3_annotation_oracle import reference_annotation
from algo07v3_inventory_oracle import original_inventory
from check_algo07v3_scan_likelihood import fingerprint


def original_callable(function, **overrides):
    class ExplicitIO(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call):
                f = node.value.func
                if (isinstance(f, ast.Name) and f.id == "print") or (
                    isinstance(f, ast.Attribute) and f.attr == "mkdir"
                ):
                    return None
            return self.generic_visit(node)

        def visit_Assign(self, node):
            # The synthetic trial has no on-disk file. Bind all actual sources
            # and inputs separately in the oracle receipt instead.
            if any(
                isinstance(t, ast.Subscript)
                and isinstance(t.value, ast.Name)
                and t.value.id == "hashes"
                for t in node.targets
            ):
                return None
            return self.generic_visit(node)

    tree = ExplicitIO().visit(ast.parse(inspect.getsource(function)))
    namespace = dict(function.__globals__, **overrides)
    exec(
        compile(ast.fix_missing_locations(tree), inspect.getsourcefile(function), "exec"), namespace
    )
    return namespace[function.__name__]


def reference_inclusion(context, inventory, annotation):
    import algo03_shadow_worker as controller
    import audit_predictive_family_inclusion as new_audit
    import audit_shared_predictive_inclusion as shared_audit
    import include_new_predictive_family as new_fit
    import include_predictive_annotations as shared_fit
    from annotation_partition_plan import require_distinct_annotation
    from retry_predictive_numerical_failures import numerical_only
    from test_predictive_graph_transfer import shared_family_route

    from leo.analysis.research.grouped_prediction import identity_consensus

    vote = identity_consensus(annotation["result"]["folds"], score_name="conditional_target")
    if vote["status"] != "conditionally_supported_identity":
        return dict(status=vote["status"], annotation=vote, selected=None)
    # Production applies this before dispatching inclusion.
    require_distinct_annotation(annotation["result"], annotation["protocol"])
    if annotation["result"].get("inactive_graph_fragment"):
        raise ValueError("External inclusion oracle currently qualifies whole-track targets only")
    shared = shared_family_route(annotation["result"]["folds"], vote["norad"])
    folder = Path("/explicit-validation") / annotation["result"]["track_id"]
    trial_path = Path("/explicit-trial")
    inv = dict(inventory, job=dict(job_id="external-oracle", label="SCAN"))

    def execute(optimizer):
        records = {
            folder / "protocol.json": annotation["protocol"],
            folder / "result.json": annotation["result"],
        }

        def read(path):
            return inv if path.name == "inventory.json" else deepcopy(records[path])

        def write(path, value):
            records[path] = deepcopy(value)

        overrides = dict(read=read, write=write, context=lambda _: context)
        args = SimpleNamespace(
            inventory=Path("/inventory.json"),
            output=trial_path,
            validation=[folder],
            native_branches=None,
            predictive_member=True,
            orphan_phase_refresh=False,
            orphan_orbit_prior=False,
            uncalibrated_label=True,
            phase_step=0.025,
            omit_orbit_uncertainty=False,
            omit_receiver_uncertainty=False,
            skip_phase_audit=False,
            optimizer=optimizer,
        )
        original_callable((shared_fit if shared else new_fit).run, **overrides)(args)
        original_callable((shared_audit if shared else new_audit).run, **overrides)(
            SimpleNamespace(
                trial=trial_path,
                study=Path("/study"),
                output=trial_path / "exact_owner_replay.json",
            )
        )
        selected = original_callable(
            controller.single_candidate, read=read, scientific_receipts=lambda _: {}
        )(inv, trial_path, shared)
        if selected:
            selected = {k: v for k, v in selected.items() if k not in ("trial", "source_receipts")}
        trial = {
            p.stem: {k: v for k, v in r.items() if k not in ("job", "seconds")}
            for p, r in records.items()
            if p.parent == trial_path and p.stem != "exact_owner_replay"
        }
        protocol = trial["protocol"]
        if "annotation_receipts" in protocol:
            protocol["annotation_receipts"] = [
                {k: v for k, v in r.items() if k != "path"} for r in protocol["annotation_receipts"]
            ]
        if "validation" in protocol:
            protocol["validation"] = [Path(p).name for p in protocol["validation"]]
        audit = {
            k: v
            for k, v in records[trial_path / "exact_owner_replay.json"].items()
            if k != "source_hashes"
        }
        return trial, audit, selected

    trial, audit, selected = execute("lbfgsb")
    result = dict(annotation=vote, shared_family=shared, trial=trial, audit=audit, retry=None)
    if (
        not shared
        and selected is None
        and numerical_only(trial["control"], trial["new_family"], audit)
    ):
        retry, replay, selected = execute("powell")
        result["retry"] = dict(trial=retry, audit=replay)
    result.update(
        status="qualified_candidate" if selected else "inclusion_rejected", selected=selected
    )
    return result


def run(args):
    sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
    import algo03_inventory
    import annotate_predictive_only
    import inventory_all_large_tracks
    from algo03_shadow_worker import select_targets
    from benchmark_graph_covariance import baseline_pair, load_case
    from debug_fast_graph_unassociated import memberships

    started = time.monotonic()
    context = load_case(args.source.parent, args.source.name)
    pair = baseline_pair(context)
    owners = {
        a: memberships(p, x, context["entries"])[3] for a, (p, x) in context["problems"].items()
    }
    observations = json.loads((args.source / "observations.json").read_bytes())
    inv = original_inventory(
        inventory_all_large_tracks, context["scan"].tracks, observations, pair, args.scan_identities
    )
    inv["publication_support"] = algo03_inventory.publication_support(
        dict(arms=context["saved"]["policy_arms"]), owners
    )
    target = select_targets(inv)[0][args.target_rank]
    annotation = reference_annotation(annotate_predictive_only, context, inv, target)
    inclusion = reference_inclusion(context, inv, annotation)
    output = dict(predictive_annotation=annotation, predictive_inclusion=inclusion)
    args.output.write_text(json.dumps(fingerprint(output), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    inputs = list(args.source.glob("*")) + list(
        (args.source.parent / "causal_prior" / args.source.name).glob("*")
    )
    inputs += [args.source.parent / "family_cavity" / "position" / (args.source.name + ".json")]
    modules = {
        n: binding(m.__file__)
        for n, m in sys.modules.items()
        if getattr(m, "__file__", None)
        and (
            str(m.__file__).startswith(str(args.runtime))
            or n
            in (
                "algo07v3_annotation_oracle",
                "algo07v3_inventory_oracle",
                "check_algo07v3_scan_likelihood",
            )
        )
    }
    receipt = dict(
        seconds=time.monotonic() - started,
        source=str(args.source),
        output=binding(args.output),
        tool=binding(__file__),
        modules=modules,
        inputs=[binding(p) for p in inputs if p.is_file()],
        scan_identities=args.scan_identities,
        target_rank=args.target_rank,
        track_id=target["track_id"],
        status=inclusion["status"],
        retry=inclusion.get("retry") is not None,
        operational_normalization=[
            "job",
            "seconds",
            "annotation_receipts.path",
            "validation folder to track ID",
            "source_hashes",
            "selected.trial",
            "selected.source_receipts",
        ],
    )
    args.output.with_suffix(".receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps({k: receipt[k] for k in ("seconds", "track_id", "status", "retry", "output")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scan-identities", nargs="+", required=True)
    parser.add_argument("--target-rank", type=int, default=0)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Inclusion output already exists")
    run(args)
