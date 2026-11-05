"""Replay the selected incumbent and nominate unused native graph supports.

All inputs are owned in-memory evidence and the preceding cavity decision.
No historical result, installation, storage reader or evaluation site is used.
The inventory includes postfit-only associations, while publication ownership
protects the subset actually reported by the preceding scientific policy.
"""

import hashlib
from copy import deepcopy

import numpy as np

from leo.analysis.localization_v3.acceptance import extend_associations
from leo.analysis.localization_v3.cavity_prediction import legacy_phase_reference
from leo.analysis.localization_v3.conservative_recovery import retained_metrics
from leo.analysis.localization_v3.event_position import (
    attach_event_predictive,
    cached,
    make_event_problem,
    summary,
)

ARMS = ("c0", "fitted_c")


def recovery_context(scan, saved):
    """Reconstruct both likelihoods and verify the saved selected objectives."""
    if saved["status"] != "complete":
        raise ValueError("complete cavity decision required")
    chosen = saved["selected"] if saved["accepted"] else None
    node = deepcopy(chosen["node"] if chosen else saved["baseline_node"])
    entries = deepcopy(chosen["entries"] if chosen else saved["baseline_entries"])
    means = np.array(chosen["means"] if chosen else saved["baseline_means"], copy=True)
    keep = np.array(saved["original_mask"], bool, copy=True)
    powers = np.array(saved["powers"], copy=True)
    model = deepcopy(saved["model"])

    def build(arm, reference):
        p = make_event_problem(
            scan, node, keep, arm, np.asarray(reference), powers, means, model, []
        )
        attach_event_predictive(p, entries, powers)
        return p

    problems, replay = {}, {}
    for arm in ARMS:
        row = saved["policy_arms"][arm]
        x = np.array(row["endpoint_east_north_km"], copy=True)
        p = build(arm, row["phase_reference"])
        delta = p.calculate(x)["negative_twice_elbo"] - row["negative_twice_elbo"]
        if abs(delta) > 1e-5:

            def posterior(reference, parameters, arm=arm):
                probe = build(arm, reference)
                return probe.state(parameters)["phases"][probe.labels]

            reference = legacy_phase_reference(row["history"], np.zeros(len(means)), posterior)
            p = build(arm, reference)
            delta = p.calculate(x)["negative_twice_elbo"] - row["negative_twice_elbo"]
        if not np.isfinite(delta) or abs(delta) > 1e-5:
            raise ValueError(f"baseline replay mismatch {arm}: {delta}")
        problems[arm] = (cached(p), x)
        replay[arm] = float(delta)
    return dict(
        scan=scan,
        node=node,
        entries=entries,
        means=means,
        keep=keep,
        powers=powers,
        model=model,
        problems=problems,
        original={a: p for a, (p, _) in problems.items()},
        saved=saved,
        replay=replay,
        support_policy="nominal",
    )


def memberships(p, x, entries):
    metrics = retained_metrics(p, x)
    curved = {
        oid
        for i, sl in zip(p.members, p.slices, strict=True)
        for oid, use in zip(p.scan.tracks[i]["observation_ids"], p.keep[sl], strict=True)
        if use
    }
    predictive = {oid for entry in entries for oid in entry["observation_ids"]}
    extension = extend_associations(p, x, metrics)
    lookup = {t["key"]: t for t in p.scan.tracks}
    accepted = curved | predictive
    owners = {}
    for row in extension["tracks"]:
        if not row["compatible"]:
            continue
        ids = row.get("observation_ids", lookup[row["component"]]["observation_ids"])
        if set(ids) & predictive:
            continue
        accepted.update(ids)
        for oid in ids:
            owners[oid] = row["norad"]
    for entry in entries:
        for oid in entry["observation_ids"]:
            owners[oid] = entry["norad"]
    return curved, predictive, accepted, owners


def baseline_pair(context):
    pair, owners = {}, {}
    for arm, (p, x) in context["problems"].items():
        row = summary(p, x, context["entries"])
        curved, predictive, ids, owners[arm] = memberships(p, x, context["entries"])
        row.update(
            curved_points=len(curved),
            predictive_points=len(predictive),
            postfit_only_points=len(ids - curved - predictive),
            proposed_associated_points=len(ids),
            proposed_associated_ids=sorted(ids),
            final_phase_change_s=context["saved"]["policy_arms"][arm].get(
                "final_phase_change_s", 0.0
            ),
        )
        pair[arm] = row
    return pair, owners


def publication_support(arms, replayed):
    """Protect reported owners; distinguish additional frozen-fit extensions."""
    result = {}
    for arm in ARMS:
        actual, published, known = replayed[arm], set(), {}
        for track in arms[arm]["gates"]["tracks"] + arms[arm].get("linear_gates", []):
            for oid in track["observation_ids"]:
                published.add(oid)
                if track.get("norad") is not None:
                    if oid in known and known[oid] != track["norad"]:
                        raise ValueError("Conflicting published baseline owner")
                    known[oid] = track["norad"]
        if not published <= actual.keys() or any(actual[o] != n for o, n in known.items()):
            raise ValueError("Published baseline does not replay its original ownership")
        result[arm] = dict(
            owners={o: actual[o] for o in sorted(published)},
            unreported_postfit_ids=sorted(actual.keys() - published),
        )
    if result["c0"]["owners"] != result["fitted_c"]["owners"]:
        raise ValueError("Published c-arm ownership differs")
    return result


def remaining_track(track, associated):
    mask = np.array([oid not in associated for oid in track["observation_ids"]])
    if mask.sum() < 2:
        return None
    times = np.asarray(track["times"])[mask]
    values = np.asarray(track["values"])[mask]
    x = times - times.mean()
    centered = values - values.mean()
    residual = centered - x * (x @ centered) / max(x @ x, 1e-12)
    duration = float(np.ptp(times))
    curvature = float(np.sqrt(np.mean(residual**2)))
    return dict(
        component=track["key"],
        receiver=track["receiver"],
        channel=track["channel"],
        unassociated_points=int(mask.sum()),
        total_track_points=len(mask),
        start_s=float(times.min()),
        end_s=float(times.max()),
        span_s=duration,
        largest_gap_s=float(np.diff(np.sort(times)).max()),
        wholly_unassociated=bool(mask.all()),
        remaining_detrended_RMS_hz=curvature,
        active_curvature=bool(duration >= 20 and curvature >= 250),
        polynomial_RMS_hz=track["residual_rms_hz"],
        pieces=len(track["pieces"]),
        quality_status=track["quality_status"],
        big=bool(mask.sum() >= 20 and duration >= 20),
    )


def inventory(tracks, observations, current, *, identities):
    """Inventory the initial recovery incumbent; no prior recovered policy yet."""
    all_ids = {o["observation_id"] for o in observations}
    graph_ids = {o for t in tracks for o in t["observation_ids"]}
    rows, totals = [], []
    for arm in ARMS:
        owned = set(current[arm]["proposed_associated_ids"])
        if not owned <= all_ids:
            raise ValueError("unknown accepted observation IDs")
        local = []
        for i, track in enumerate(tracks):
            remaining = remaining_track(track, owned)
            if remaining is None:
                continue
            ids = sorted(set(track["observation_ids"]) - owned)
            track_id = hashlib.sha256(
                (
                    "\n".join(identities) + "\n" + "\n".join(sorted(track["observation_ids"]))
                ).encode()
            ).hexdigest()[:20]
            local.append(
                dict(
                    track_id=track_id,
                    arm=arm,
                    component=track["key"],
                    track_index=i,
                    observation_ids=ids,
                    all_track_observation_ids=track["observation_ids"],
                    current=remaining,
                    earlier=deepcopy(remaining),
                    earlier_large=bool(remaining["big"]),
                    current_large=bool(remaining["big"]),
                    recovered_points=0,
                )
            )
        large_ids = {o for r in local if r["current_large"] for o in r["observation_ids"]}
        totals.append(
            dict(
                arm=arm,
                total_GLRT=len(all_ids),
                associated=len(owned),
                unassociated=len(all_ids - owned),
                graph_tracks=len(tracks),
                large_tracks=sum(r["current_large"] for r in local),
                large_track_unique_points=len(large_ids),
                unassociated_outside_graph=len(all_ids - owned - graph_ids),
                recovered_previously_large=0,
            )
        )
        rows.extend(local)
    return dict(summary=totals, tracks=rows, policy=current, prior_policy=current)


def select_targets(inv, limit=8):
    by_arm = {a: {r["track_id"]: r for r in inv["tracks"] if r["arm"] == a} for a in ARMS}
    selected = []
    for tid, row in by_arm["c0"].items():
        other = by_arm["fitted_c"].get(tid)
        if other is None or not all(r["current_large"] for r in (row, other)):
            continue
        ids = set(row["observation_ids"])
        if ids != set(other["observation_ids"]) or not ids <= set(row["all_track_observation_ids"]):
            continue
        selected.append(dict(row, inactive_fragment=ids != set(row["all_track_observation_ids"])))
    selected.sort(key=lambda r: (-len(r["observation_ids"]), r["track_id"]))
    return selected[:limit], len(selected)


def prepare_recovery(scan, cavity, observations, *, identities):
    context = recovery_context(scan, cavity)
    pair, owners = baseline_pair(context)
    support = publication_support(cavity["policy_arms"], owners)
    inv = inventory(scan.tracks, observations, pair, identities=identities)
    selected, eligible = select_targets(inv)
    result = dict(
        inventory=inv,
        publication_support=support,
        owners=owners,
        baseline_objective_replay=context["replay"],
        selected_targets=selected,
        eligible_targets=eligible,
    )
    return context, result
