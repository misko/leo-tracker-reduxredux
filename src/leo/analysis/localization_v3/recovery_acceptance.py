"""Scientific adoption rules for independently scored recovery additions."""

import math

from leo.analysis.localization_v3.history_policy import pair_passes

ARMS = ("c0", "fitted_c")


def single_candidate(inventory, trial, audit, shared):
    control = trial["control"]
    addition = trial["target_0" if shared else "new_family"]
    if not (control["paired_valid"] and addition["paired_valid"] and audit["all_verified"]):
        return None
    if shared:
        for document in (control, addition):
            for arm in ARMS:
                history = document["arms"][arm].get("history", [])
                if not history:
                    return None
                fit = history[-1].get("fit", {})
                completed = (
                    fit["success"] is True
                    if "success" in fit
                    else fit.get("stopped") == "small_step_and_improvement"
                )
                if not completed:
                    return None
    role = "target_0" if shared else "new_family"
    rows = {r["arm"]: r for r in audit["rows"] if r["role"] == role}
    owners = {
        a: addition["arms"][a]["proposed_owners"] if shared else rows[a]["owners"] for a in ARMS
    }
    protocol = trial["protocol"]
    pair = scoped_pair(inventory, addition["arms"], owners, protocol["targets"])
    return dict(
        kind="shared_family" if shared else "new_family",
        arms=pair,
        targets=protocol["targets"],
        inactive_fragment=bool(protocol.get("inactive_fragment_sources")),
    )


def shared_family_route(folds, norad):
    kinds = {
        q["arms"][arm]["prior"]["kind"]
        for f in folds
        for q in f["proposals"]
        if q["norad"] == norad
        for arm in ("c0", "fitted_c")
    }
    known = {
        "existing_shared_posterior",
        "new_family_causal_phase_mixture",
        "uncalibrated_family_causal_phase_mixture",
    }
    if not kinds or not kinds <= known:
        raise ValueError("unknown or missing winning predictive prior")
    return "existing_shared_posterior" in kinds


def scoped_pair(inventory, arms, owners, targets):
    """Credit only original incumbent IDs plus the explicitly scored targets."""
    wanted_targets = {o for t in targets for o in t["observation_ids"]}
    if len(wanted_targets) != sum(len(t["observation_ids"]) for t in targets):
        raise ValueError("Duplicate target observation")
    pair = {}
    for arm in ARMS:
        old = (
            set(inventory["publication_support"][arm]["owners"])
            if "publication_support" in inventory
            else set(inventory["policy"][arm]["proposed_associated_ids"])
        )
        wanted = old | wanted_targets
        if old & wanted_targets or not wanted <= set(owners[arm]):
            raise ValueError("Lost incumbent or overlapping/unverified target")
        for t in targets:
            if any(owners[arm][o] != t["norad"] for o in t["observation_ids"]):
                raise ValueError("Target ownership differs from scored satellite")
        xy = arms[arm]["endpoint_east_north_km"]
        if len(xy) != 2 or not all(math.isfinite(v) and abs(v) <= 12.5 for v in xy):
            raise ValueError("Invalid regional endpoint")
        pair[arm] = dict(
            endpoint_east_north_km=xy,
            endpoint_latlon=arms[arm]["endpoint_latlon"],
            negative_twice_elbo=arms[arm]["negative_twice_elbo"],
            associated_ids=sorted(wanted),
            owners={o: owners[arm][o] for o in sorted(wanted)},
            added_points=len(wanted_targets),
        )
    if pair["c0"]["owners"] != pair["fitted_c"]["owners"]:
        raise ValueError("Paired observation identities or satellites differ")
    return pair


def joint_pair(candidates):
    """Choose one disjoint native pair by scored support, never location error."""
    pairs = []
    for i, first in enumerate(candidates):
        for second in candidates[i + 1 :]:
            pair = [first, second]
            if any(q["kind"] != "new_family" or q.get("inactive_fragment") for q in pair):
                continue
            if first["targets"][0]["norad"] == second["targets"][0]["norad"]:
                continue
            ids = [o for q in pair for t in q["targets"] for o in t["observation_ids"]]
            if len(ids) == len(set(ids)):
                pairs.append((len(ids), pair))
    return max(pairs, key=lambda p: p[0])[1] if pairs else []


def owner_changes(before, after):
    return [
        dict(observation_id=o, before=n, after=after.get(o))
        for o, n in before.items()
        if after.get(o) != n
    ]


def numerical_only(control, addition, replay):
    pairs = (control["arms"], addition["arms"])
    return bool(
        replay.get("all_verified")
        and (not (control["paired_valid"] and addition["paired_valid"]))
        and all(pair_passes(pair, include_linear=True) for pair in pairs)
        and all(v["lost_points"] == 0 for pair in pairs for v in pair.values())
        and any(not v["history"][-1]["success"] for pair in pairs for v in pair.values())
        and all(
            v["phase_resolution_audit"]["local_agreement"]
            and v["family"]["phase_boundary_mass"] < 0.01
            for v in addition["arms"].values()
        )
    )
