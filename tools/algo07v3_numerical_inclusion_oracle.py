"""Frozen numerical inclusion oracle for an unchanged, nonoverflowing annotation.

This is an external reference adapter. The candidate engine never imports it.
Shared fits follow the original reuse rule; new-family fits use the pinned
numerical policy. Annotation-overflow replay is qualified separately.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import algo07v3_inclusion_oracle as oracle


def run(args):
    sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
    from algo04_numerical_helper import patched_stages
    from algo04_replay_worker import overflow
    from test_predictive_graph_transfer import shared_family_route

    from leo.analysis.research.grouped_prediction import identity_consensus

    original = oracle.reference_inclusion

    def numerical(context, inventory, annotation):
        if overflow(annotation["result"]):
            raise ValueError("This fixture requires a separate frozen-competition replay")
        vote = identity_consensus(annotation["result"]["folds"], score_name="conditional_target")
        if shared_family_route(annotation["result"]["folds"], vote["norad"]):
            raise ValueError("Use the original shared-stage oracle for the reused fixture")
        with patched_stages(reference_limit_s=30, centered_lbfgsb=True) as state:
            result = original(context, inventory, annotation)
            result["numerical_policy"] = {
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
            return result

    oracle.reference_inclusion = numerical
    try:
        oracle.run(args)
    finally:
        oracle.reference_inclusion = original
    receipt_path = args.output.with_suffix(".receipt.json")
    receipt = json.loads(receipt_path.read_text())
    receipt["numerical_adapter"] = dict(
        path=__file__, sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    )
    receipt["scope"] = "Fresh frozen numerical new-family trial for a nonoverflowing annotation"
    receipt["full_pipeline_parity"] = False
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scan-identities", nargs="+", required=True)
    parser.add_argument("--target-rank", type=int, default=1)
    run(parser.parse_args())
