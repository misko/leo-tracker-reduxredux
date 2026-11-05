"""Fresh conditional gap fit/audit oracle using an explicit sealed annotation.

Reference IO is captured in memory. The candidate consumes explicit scientific
inputs and runs with old installations inaccessible, including both c arms.
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
        path = Path(path)
        raw = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    started = time.monotonic()
    inventory = read(args.inventory)
    observations = read(args.source / "observations.json")
    annotation = {key: read(args.annotation / (key + ".json")) for key in ("protocol", "result")}
    source = dict(
        protocol=read(args.original_source.parent / "protocol.json"), **read(args.original_source)
    )
    # Preserve and bind these external provenance fields separately. The new
    # engine receives data and a canonical digest rather than legacy paths.
    source["protocol"].pop("job")
    source["protocol"].pop("input_sha256")
    if args.side == "candidate":
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3.gap_fragments import gap_context
        from leo.analysis.localization_v3.gap_recovery import audit_gap, fit_gap

        context = owned_context(args.source, bindings)
        _, target = gap_context(
            context, inventory, source, annotation["result"]["track_id"], observations
        )
        old = annotation["protocol"]["target"]
        for key in set(old) - {"native_branch_source", "native_branch_sha256"}:
            if fingerprint(old[key]) != fingerprint(target[key]):
                raise ValueError("Native annotation scientific target differs: " + key)
        annotation["protocol"]["target"] = target
        annotation["gap_source"] = source
        trial, fit_numerics = fit_gap(context, inventory, annotation, observations)
        audit, audit_numerics = audit_gap(context, inventory, annotation, trial, observations)
    else:
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        import algo05_gap_stage as gap
        import audit_shared_predictive_inclusion as audit_module
        import include_predictive_annotations as fit_module
        import native_predictive_branch
        from algo04_numerical_helper import patched_stages
        from benchmark_graph_covariance import load_case

        context = load_case(args.source.parent, args.source.name)
        native_predictive_branch.native_context = gap.gap_context
        records = {}
        out = Path("/explicit-trial")

        def read_record(path):
            return deepcopy(records[path]) if path in records else read(path)

        def write(path, value):
            records[path] = deepcopy(value)

        def numerical_receipt(state):
            return {
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

        with patched_stages(reference_limit_s=30, centered_lbfgsb=True) as state:
            original_callable(
                fit_module.run, read=read_record, write=write, context=lambda _: context
            )(
                SimpleNamespace(
                    inventory=args.inventory,
                    output=out,
                    validation=[args.annotation],
                    native_branches=None,
                    native_from_validation=True,
                    predictive_member=False,
                    orphan_phase_refresh=False,
                    orphan_orbit_prior=False,
                    conditional_satellite_refresh=True,
                )
            )
            fit_numerics = numerical_receipt(state)
        appended, _ = gap.gap_context(
            context, inventory, args.original_source, annotation["result"]["track_id"]
        )

        def audit_read(path):
            return inventory if path.name == "inventory.json" else read_record(path)

        with patched_stages(reference_limit_s=30, centered_lbfgsb=True) as state:
            original_callable(
                audit_module.run, read=audit_read, write=write, context=lambda _: appended
            )(SimpleNamespace(trial=out, study=Path("/explicit-study"), output=out / "audit.json"))
            audit_numerics = numerical_receipt(state)
        trial = {p.stem: v for p, v in records.items() if p.name != "audit.json"}
        audit = records[out / "audit.json"]
    for row in trial.values():
        row.pop("job", None)
        row.pop("seconds", None)
    protocol = trial["protocol"]
    for receipt in protocol["annotation_receipts"]:
        receipt.pop("path", None)
    if len(protocol["native_sources"]) != 1:
        raise ValueError("Expected one sealed gap source")
    protocol["native_sources"] = ["explicitly_bound_gap_source"]
    audit.pop("source_hashes", None)
    result = dict(
        trial=trial, audit=audit, fit_numerics=fit_numerics, audit_numerics=audit_numerics
    )
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
        scope="Fresh conditional gap inclusion and exact owner/orbit audit only",
        full_pipeline_parity=False,
        excluded_fields=[
            "trial.*.job",
            "trial.*.seconds",
            "trial.protocol.annotation_receipts.path",
            "trial.protocol.native_sources",
            "audit.source_hashes",
        ],
    )
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                side=args.side,
                seconds=receipt["seconds"],
                paired_valid=bool(trial["target_0"]["paired_valid"]),
                all_verified=bool(audit["all_verified"]),
                output=receipt["output"],
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["candidate", "reference"], required=True)
    for field in ("source", "inventory", "runtime", "output", "original-source", "annotation"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Gap inclusion oracle output already exists")
    run(args)
