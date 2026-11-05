"""Strict comparison of reconstructed likelihoods and native residual preflight."""

from compare_algo07v3_inclusion import first_difference

KINDS = dict(baseline="baseline", single="new_family", joint="joint", gap="gap_conditional")


def compare(reference, candidate, mode):
    difference = first_difference(reference, candidate)
    if difference:
        raise ValueError("Selected likelihood/preflight differs: " + str(difference))
    if set(candidate["checks"]) != {"c0", "fitted_c"}:
        raise ValueError("Both calibration arms required")
    for arm, row in candidate["checks"].items():
        if row["selected_kind"] != KINDS[mode]:
            raise ValueError("Wrong reconstruction branch")
        for name in ("incumbent_core_objective_difference", "full_selected_likelihood_difference"):
            if float.fromhex(row[name]["hex"]) != 0:
                raise ValueError("Fixture selected objective did not replay exactly")
        if not candidate["arms"][arm]["offset_calculation"]:
            raise ValueError("Missing nearby-position likelihood probe")
    ranked = candidate["residual_inventory"]
    if [t["source"] for t in candidate["preflight"]["targets"]] != ranked["targets"]:
        raise ValueError("Preflight does not follow the ranked target list")
    summary = ranked["summary"]
    if sum(r["points"] for r in ranked["fragments"]) != summary["residual_graph_unique_points"]:
        raise ValueError("Residual graph evidence lost or duplicated")
    return dict(
        exact=True,
        kind=KINDS[mode],
        total_GLRT=summary["total_GLRT"],
        retained_points={a: r["associated_points"] for a, r in candidate["checks"].items()},
        incidental_uncredited={
            a: r["incidental_unpublished_extensions_not_adopted"]
            for a, r in candidate["checks"].items()
        },
        residual_graph_points=summary["residual_graph_unique_points"],
        unassociated_untracked_points=summary["unassociated_untracked_points"],
        eligible_fragments=ranked["eligible_targets"],
        nominated_fragments=len(ranked["targets"]),
        nominated_points=sum(r["points"] for r in ranked["targets"]),
        full_pipeline_parity=False,
    )
