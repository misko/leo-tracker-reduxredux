"""Match single-family controller selection to independently qualified references.

This covers complete target enumeration on a fixture with exactly one qualified
individual and no eligible joint pair. Joint numerical equivalence is separate.
"""

import argparse
import hashlib
import json
from pathlib import Path

from compare_algo07v3_inclusion import first_difference

from leo.contracts.fast_graph_position_v2 import RF_CHECKS


def compare(candidate, inventory_prefix, references):
    prefix = {k: v for k, v in candidate.items() if k != "predictive_recovery"}
    difference = first_difference(inventory_prefix, prefix)
    if difference:
        raise ValueError("Preceding prefix changed: " + difference)
    evidence = inventory_prefix["recovery_inventory"]
    targets = evidence["selected_targets"]
    if len(targets) != len(references):
        raise ValueError("Every selected target needs its independent reference")
    attempts, stages, qualified = [], [], []
    for i, (target, reference) in enumerate(zip(targets, references, strict=True)):
        annotation = reference["predictive_annotation"]
        inclusion = reference["predictive_inclusion"]
        if target["track_id"] != annotation["result"]["track_id"]:
            raise ValueError("Reference target order differs")
        attempt = dict(
            track_id=target["track_id"],
            points=len(target["observation_ids"]),
            annotation=inclusion["annotation"],
        )
        stages.append(dict(name=f"target-{i}-annotation", status="complete"))
        if inclusion["annotation"]["status"] != "conditionally_supported_identity":
            attempt["status"] = inclusion["annotation"]["status"]
        else:
            attempt["shared_family"] = inclusion["shared_family"]
            stages += [
                dict(name=f"target-{i}-{s}", status="complete") for s in ("inclusion", "audit")
            ]
            if inclusion["retry"] is not None:
                attempt["numerical_retry"] = True
                stages += [
                    dict(name=f"target-{i}-{s}", status="complete")
                    for s in ("retry", "retry-audit")
                ]
            attempt["status"] = "RF_qualified" if inclusion["selected"] else "RF_rejected"
            if inclusion["selected"]:
                qualified.append(inclusion["selected"])
        attempts.append(attempt)
    if len(qualified) != 1:
        raise ValueError("This fixture comparison requires exactly one qualified individual")
    expected = dict(
        decision="ALGO03_single",
        selected=qualified[0],
        attempts=attempts,
        stages=stages,
        source_support=evidence["publication_support"],
        inventory_summary=evidence["inventory"]["summary"],
        eligible_tracks=evidence["eligible_targets"],
        selected_track_ids=[t["track_id"] for t in targets],
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
        rf_checks={k: True for k in RF_CHECKS},
    )
    difference = first_difference(expected, candidate["predictive_recovery"])
    if difference:
        raise ValueError("Controller scientific decision differs: " + difference)
    return dict(
        exact=True,
        unchanged_prefix=True,
        all_selected_targets_compared=True,
        selected_kind=qualified[0]["kind"],
        full_pipeline_parity=False,
        ordinary_clock_policy_qualified=False,
        scope="Fresh complete target loop with one individually qualified family; test admission",
    )


def run(args):
    paths = [args.candidate, args.inventory_prefix, *args.references]
    raw = [p.read_bytes() for p in paths]
    documents = [json.loads(v) for v in raw]
    result = compare(documents[0], documents[1], documents[2:])
    result["inputs"] = [
        dict(path=str(p), sha256=hashlib.sha256(b).hexdigest())
        for p, b in zip(paths, raw, strict=True)
    ]
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "inventory-prefix", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--references", type=Path, nargs="+", required=True)
    run(parser.parse_args())
