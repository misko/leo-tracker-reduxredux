"""Exact scientific gates for selected-checkpoint and causal-screen extraction."""

from compare_algo07v3_inclusion import first_difference


def exact(left, right, label):
    difference = first_difference(left, right)
    if difference:
        raise ValueError(label + ": " + str(difference))


def number(value):
    return float.fromhex(value["hex"]) if isinstance(value, dict) else float(value)


def compare_screen(reference, candidate):
    exact(reference, candidate, "Residual screen changed")
    rows = []
    for target in candidate["targets"]:
        summary = next(s for s in target["summaries"] if s["policy"] == "72h_30s")
        if set(summary["arms"]) != {"c0", "fitted_c"}:
            raise ValueError("Both screen arms required")
        arms = {}
        for arm, evidence in summary["arms"].items():
            folds = evidence["folds"]
            full = folds.get("full", {}).get("winner")
            arms[arm] = dict(
                full_winner=full["norad"] if full else None,
                phase_s=number(full["phase_s"]) if full else None,
                rms_hz=number(full["rms_hz"]) if full else None,
                minimum_margin=min((number(f["margin"]) for f in folds.values()), default=None),
                qualified=evidence["qualified"],
                folds=len(folds),
            )
        if summary["screen_pass"] and (
            any(not a["qualified"] or a["folds"] != 4 for a in arms.values())
            or len({a["full_winner"] for a in arms.values()}) != 1
        ):
            raise ValueError("Passed screen lacks matched independent identity evidence")
        rows.append(
            dict(
                fragment_id=target["source"]["fragment_id"],
                receiver=target["source"]["receiver"],
                channel=target["source"]["channel"],
                points=target["source"]["points"],
                duration_s=number(target["source"]["duration_s"]),
                finalists=target["finalists"],
                screen_pass=summary["screen_pass"],
                arms=arms,
            )
        )
    return dict(
        exact=True,
        catalogue_count=candidate["catalogue_count"],
        targets=rows,
        passed_tracks=sum(r["screen_pass"] for r in rows),
        screen_pass_points=sum(r["points"] for r in rows if r["screen_pass"]),
        newly_associated_points=0,
        full_pipeline_parity=False,
    )


def compare_prefix(previous, candidate):
    exact(
        previous,
        {k: v for k, v in candidate.items() if k not in ("additional_recovery", "residual_screen")},
        "Earlier implemented prefix changed",
    )
    prepared = candidate["additional_recovery"]
    if prepared["status"] != "additional_recovery_prepared" or prepared["recovery_complete"]:
        raise ValueError("Wrong additional-preparation state")
    numerical, gap = candidate["numerical_recovery"], candidate["gap_recovery"]
    if gap["candidate"]:
        old = {a: r["proposed_owners"] for a, r in gap["candidate"]["trial"]["arms"].items()}
    else:
        support = (
            numerical["selected"]["arms"]
            if numerical["selected"]
            else numerical["retained"]["source_support"]
        )
        old = {a: r["owners"] for a, r in support.items()}
    exact(old, prepared["selected_owners"], "Selected ownership changed across checkpoint")
    for arm, check in prepared["replay_checks"].items():
        if (
            number(check["full_selected_likelihood_difference"]) != 0
            or number(check["incumbent_core_objective_difference"]) != 0
        ):
            raise ValueError("Selected checkpoint likelihood did not replay exactly")
        if check["associated_points"] != len(old[arm]):
            raise ValueError("Reconstruction changed credited point count")
    occupied = set().union(*(set(v) for v in old.values()))
    if any(set(t["observation_ids"]) & occupied for t in prepared["inventory"]["targets"]):
        raise ValueError("Selected checkpoint re-nominates an owned point")
    return dict(
        prefix_exact=True,
        retained_points={a: len(v) for a, v in old.items()},
        incidental_uncredited={
            a: r["incidental_unpublished_extensions_not_adopted"]
            for a, r in prepared["replay_checks"].items()
        },
        nominated_fragments=len(prepared["inventory"]["targets"]),
        full_pipeline_parity=False,
    )
