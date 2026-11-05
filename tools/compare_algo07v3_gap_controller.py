"""Strict gap-controller fixture and unchanged preceding-prefix comparisons."""

from compare_algo07v3_inclusion import first_difference


def exact(expected, actual, label):
    difference = first_difference(expected, actual)
    if difference:
        raise ValueError(label + ": " + difference)


def compare_controller(reference, candidate):
    exact(reference, candidate, "Gap controller changed")
    if not candidate.get("no_GPS_inference") or not candidate.get("causal_only"):
        raise ValueError("Causal/no-GPS guarantees missing")
    selected = candidate["selected"]
    if (
        selected is None
        or selected["identity"]["norad"] != 63635
        or selected["qualification"]["added_points"] != dict(c0=95, fitted_c=95)
        or not selected["qualification"]["qualified"]
    ):
        raise ValueError("Expected DS26-0012 conditional fragment not qualified")
    exact(
        [
            dict(stage=s, completed=True, cap=c)
            for s, c in (("prepare", 180), ("annotation", 240), ("inclusion", 240), ("audit", 180))
        ],
        candidate["stages"],
        "Original stage admission changed",
    )
    if len(candidate["numerical_receipts"]) != 3:
        raise ValueError("Missing numerical stage receipts")
    proof = candidate["candidate"]
    return dict(
        exact=True,
        target_points=len(proof["target_ids"]),
        parent_points=len(proof["parent_ids"]),
        norad=selected["identity"]["norad"],
        owned_points={a: len(row["proposed_owners"]) for a, row in proof["trial"]["arms"].items()},
    )


def compare_prefix(previous, candidate):
    exact(
        previous,
        {k: v for k, v in candidate.items() if k != "gap_recovery"},
        "Earlier numerical prefix changed",
    )
    gaps = candidate["gap_recovery"]
    if not gaps["no_GPS_inference"] or not gaps["causal_only"]:
        raise ValueError("Gap inference provenance changed")
    if any(row["status"] != "complete" for row in gaps["stages"]):
        raise ValueError("Gap stage did not complete")
    numerical = candidate["numerical_recovery"]
    support = (
        numerical["selected"]["arms"]
        if numerical.get("selected")
        else numerical["retained"]["source_support"]
    )
    old = {arm: support[arm]["owners"] for arm in ("c0", "fitted_c")}
    proof = gaps["candidate"]
    adopted = (
        old
        if proof is None
        else {arm: proof["trial"]["arms"][arm]["proposed_owners"] for arm in old}
    )
    if any(adopted[arm].get(point) != sat for arm in old for point, sat in old[arm].items()):
        raise ValueError("Gap recovery loses or changes a selected numerical owner")
    return dict(
        prefix_exact=True,
        eligible_parents=len(gaps["targets"]),
        stages=len(gaps["stages"]),
        qualified=proof is not None,
        protected_points={a: len(v) for a, v in old.items()},
        resulting_points={a: len(v) for a, v in adopted.items()},
    )
