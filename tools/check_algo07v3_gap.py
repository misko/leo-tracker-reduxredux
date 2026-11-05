"""External frozen gap-fragment oracle; never imported by the candidate engine.

The candidate runs with old installations hidden. Operational source paths and
hashes are bound in separate receipts; every scientific array and fit is compared.
"""

import argparse
import hashlib
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from algo07v3_inclusion_oracle import original_callable
from check_algo07v3_scan_likelihood import fingerprint


def run(args):
    bindings = {}

    def read(path):
        raw = Path(path).read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    started = time.monotonic()
    inventory = read(args.inventory)
    observations = read(args.source / "observations.json")
    if args.side == "candidate":
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3.gap_fragments import prepare_gap
        from leo.analysis.localization_v3.gap_recovery import annotate_gap

        context = owned_context(args.source, bindings)
        source = prepare_gap(context, inventory, observations, args.parent)
        annotation, numerics = annotate_gap(context, inventory, source, args.branch, observations)
        annotation.pop("gap_source")
    else:
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        import algo05_gap_stage as gap
        import annotate_predictive_only as original
        import diagnose_all_large_tracks
        import native_predictive_branch
        from algo04_numerical_helper import patched_stages
        from benchmark_graph_covariance import load_case

        context = load_case(args.source.parent, args.source.name)
        records = {}
        diagnose_all_large_tracks.context = lambda _: context
        original_callable(
            gap.prepare,
            read=read,
            write=lambda path, value: records.update({path.name: deepcopy(value)}),
        )(dict(inventory=str(args.inventory), track_id=args.parent), Path("/explicit-gap"))
        source = dict(protocol=records["protocol.json"], **records["branches.json"])
        source["protocol"].pop("job")
        source["protocol"].pop("input_sha256")
        # The original validator requires sealed source files. Require its actual
        # numerical branch inputs to equal the freshly prepared source first.
        serialized = json.loads(json.dumps(source["branches"], default=lambda x: x.tolist()))
        if fingerprint(read(args.original_source)["branches"]) != fingerprint(serialized):
            raise ValueError("Archived gap source differs from freshly prepared branches")
        read(args.original_source.parent / "protocol.json")
        native_predictive_branch.native_context = gap.gap_context
        records = {}
        with patched_stages(reference_limit_s=30, centered_lbfgsb=True) as state:
            original_callable(
                original.run,
                read=lambda _: inventory,
                context=lambda _: context,
                write=lambda path, value: records.update({path.name: deepcopy(value)}),
            )(
                SimpleNamespace(
                    inventory=args.inventory,
                    output=Path("/explicit-annotation"),
                    track=args.branch,
                    native_branches=args.original_source,
                    inactive_fragment=False,
                    predictive_member=False,
                    distinct_partitions=True,
                    shifted_block_origin=False,
                    candidates=3,
                    folds=3,
                    phase_step=0.1,
                    uncalibrated_phase_mixture=True,
                )
            )
            numerics = {
                k: state[k]
                for k in (
                    "reference_limit_s",
                    "centered_lbfgsb",
                    "extra_optimizer_rounds",
                    "physical_priors_and_target_phase_support_unchanged",
                    "reference_updates",
                    "optimizer_calls",
                    "problem_count",
                )
            }
        annotation = dict(
            protocol=records["protocol.json"],
            result=records["result.json"],
            nominations={
                int(k.removeprefix("nominations-").removesuffix(".json")): v
                for k, v in records.items()
                if k.startswith("nominations-")
            },
            attempts={int(k[5:-5]): v for k, v in records.items() if k.startswith("seed-")},
        )
    for row in (annotation["protocol"], annotation["result"]):
        row.pop("job", None)
        row.pop("seconds", None)
    target = annotation["protocol"]["target"]
    for key in ("native_branch_source", "native_branch_sha256", "gap_source_sha256"):
        target.pop(key, None)
    result = dict(source=source, annotation=annotation, numerical_policy=numerics)
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    for directory in (args.source, args.source.parent / "causal_prior" / args.source.name):
        for path in directory.iterdir():
            if path.is_file():
                bindings[str(path)] = binding(path)["sha256"]
    cavity = args.source.parent / "family_cavity/position" / f"{args.source.name}.json"
    bindings[str(cavity)] = binding(cavity)["sha256"]
    receipt = dict(
        side=args.side,
        seconds=time.monotonic() - started,
        inputs=bindings,
        modules={
            n: binding(m.__file__)
            for n, m in sys.modules.items()
            if getattr(m, "__file__", None)
            and (
                str(m.__file__).startswith(str(args.runtime))
                or "/src/leo/" in str(m.__file__)
                or n
                in (
                    "algo07v3_inclusion_oracle",
                    "check_algo07v3_scan_likelihood",
                    "check_algo07v3_fixture_context",
                    "check_algo07v3_track_preparation",
                )
            )
        },
        tool=binding(__file__),
        output=binding(args.output),
        scope="Timing-gap preparation and fresh conditional annotation only",
        full_pipeline_parity=False,
        excluded_fields=[
            "job",
            "seconds",
            "source.protocol.input_sha256",
            "annotation.protocol.target.native_branch_source",
            "annotation.protocol.target.native_branch_sha256",
            "annotation.protocol.target.gap_source_sha256",
        ],
    )
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                side=args.side,
                seconds=receipt["seconds"],
                status=annotation["result"]["annotation"]["status"],
                output=receipt["output"],
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["candidate", "reference"], required=True)
    for field in ("source", "inventory", "runtime", "output", "original-source"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Gap oracle output already exists")
    run(args)
