"""EM-like satellite-label proposals, accepted by the complete blind objective.

Timing-linked source groups remain fixed across proposals. Curve eligibility,
point inventory and the receiver/candidate bank do not change. This heuristic
proposal/MAP-refit procedure is not an exact EM convergence proof.
"""

import argparse
import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_clock_transfer_models import mixture_cost, transfer_problem
from iterate_dsx01_position_nominations import fit_once
from iterate_dsx01_profiled_identity import explore
from prototype_dsx01_continuous_position import latlon, native_point, numpy_state
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import OUTPUT, check_pair, measurement_path, read_pairs

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency


def grouped_labels(costs, groups, current):
    """One proposed label per fixed source group, with exact disjoint coverage."""
    u = np.asarray(costs, float)
    current = np.asarray(current, int)
    if u.ndim != 2 or current.shape != (len(u),):
        raise ValueError("matching label rows required")
    flattened = [i for g in groups for i in g]
    if sorted(flattened) != list(range(len(u))):
        raise ValueError("groups must cover each curve exactly once")
    proposals = []
    for group in groups:
        old = current[group[0]]
        if np.any(current[group] != old):
            raise ValueError("source group labels must agree")
        score = np.sum(u[group], axis=0)
        new = int(np.argmin(score))
        if not np.isfinite(score[new]):
            new = int(old)
        gain = float(score[old] - score[new]) if np.isfinite(score[new]) else 0.0
        proposals.append(dict(group=list(group), old=int(old), new=new, gain=gain))
    return proposals


def fixed_pair_inventory(scan, seed, pairs):
    # Constructor eligibility is already conditioned on repeated timing links,
    # active curvature and initial blind label agreement. Freeze that layout.
    problem = transfer_problem(
        scan,
        seed,
        "receiver_smooth",
        False,
        seed["east_north_km"],
        pairs=pairs,
        mode="point_mixture",
    )
    owner = np.repeat(
        np.arange(len(problem.members)), [len(scan.tracks[i]["times"]) for i in problem.members]
    )
    groups = [
        list(map(int, np.unique(owner[positions]))) for positions, _, _, _ in problem.pair_groups
    ]
    row_by_oid = {
        oid: k for k, i in enumerate(problem.members) for oid in scan.tracks[i]["observation_ids"]
    }
    group_by_curve = {i: k for k, g in enumerate(groups) for i in g}
    fixed = [
        p
        for p in pairs
        if p["frame_coherent"]
        and p["both_original_curved"]
        and all(o in row_by_oid for o in p["observation_ids"])
        and group_by_curve[row_by_oid[p["observation_ids"][0]]]
        == group_by_curve[row_by_oid[p["observation_ids"][1]]]
    ]
    return fixed, groups


def propose(scan, incumbent, groups):
    anchor = incumbent["east_north_km"]
    state = numpy_state(incumbent["state"])
    proposal, diagnostics = explore(
        scan, state, anchor, "receiver_smooth", topk=4, maximum=64, compact_update=False
    )
    base = phase_linear_frequency(scan.geometry, *latlon(anchor))
    point = native_point(scan, anchor)
    _, _, nominees, predicted = scan.association(proposal["state"], base, point, "receiver_smooth")
    costs = []
    active_rows = [r for r in incumbent["rows"] if r["active_curvature"]]
    by_component = {track["key"]: i for i, track in enumerate(scan.tracks)}
    for row in active_rows:
        i = by_component[row["component"]]
        n = len(scan.tracks[i]["times"])
        terms = nominees[i]["terms"]
        score = min(n, 50) * np.log1p(np.maximum(0, terms["cost"]) / n)
        visible = predicted[1][:, scan.index[i]].min(axis=1) >= 0
        costs.append(np.where(visible, score, np.inf))
    costs = np.array(costs)
    sigma = np.maximum(0.1, scan.sky["phase_sigma_s"])
    prior = mixture_cost(proposal["state"]["phases"], sigma, np.maximum(3, 3 * sigma), 0.9)
    # Share the phase proposal penalty once per source group, rather than once
    # for each receiver curve. The full refit owns the actual global prior.
    for g in groups:
        costs[g] += prior / len(g)
    current = [r["candidate_index"] for r in active_rows]
    changes = grouped_labels(costs, groups, current)
    ordered = sorted(
        (p for p in changes if p["new"] != p["old"] and p["gain"] > 0), key=lambda p: -p["gain"]
    )
    candidates = {}
    for name, subset in [("top8", ordered[:8]), ("all", ordered)]:
        rows = [dict(r) for r in incumbent["rows"] if r["active_curvature"]]
        for change in subset:
            for k in change["group"]:
                j = change["new"]
                rows[k].update(candidate_index=j, candidate_norad=int(scan.norads[j]))
        candidates[name] = dict(rows=rows, state=proposal["state"])
    return candidates, dict(
        phase_exploration=diagnostics,
        changed_groups=len(ordered),
        group_proposals=[
            dict(c, gain=c["gain"] if np.isfinite(c["gain"]) else None) for c in changes
        ],
    )


def run(case, rounds=2):
    method = "receiver_smooth"
    mode = "point_mixture"
    source = measurement_path(case)
    scan = Scan(case)
    apply_measurements(scan, json.loads(source.read_text())["points"], "glrt300")
    original = OUTPUT / "priors" / case / mode / "selected.json"
    initial = json.loads(original.read_text())["glrt300"]["fits"]
    pairs, _ = read_pairs(case)
    fixed_pairs, groups = fixed_pair_inventory(scan, initial["c0"], pairs)
    directory = OUTPUT / "identity_iterations" / case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "protocol.json",
        dict(
            case=case,
            method=method,
            mode=mode,
            measurement="glrt300",
            maximum_rounds=rounds,
            initial_source=str(original),
            initial_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            group_membership_and_original_curved_observations_frozen=True,
            groups=groups,
            fixed_pair_observation_ids=[p["observation_ids"] for p in fixed_pairs],
            no_legacy_tight_radio_update=True,
            candidate_phase_hypotheses_topk=4,
            maximum_candidates=64,
            proposal_batches=["top8", "all"],
            full_c0_frequency_prior_plus_complexity_score_acceptance=True,
            exact_fitted_c_partner_follows_c0_selection=True,
            no_GPS_or_future_TLE_input=True,
            both_arms_same_labels_aliases_starts_and_24_iteration_budget=True,
        ),
    )
    path = directory / "rounds.json"
    records = json.loads(path.read_text()) if path.exists() else []
    best = initial
    for record in records:
        best = record["selected_fits"]
    for iteration in range(len(records), rounds):
        candidates, diagnostics = propose(scan, best["c0"], groups)
        attempts = {}
        for name, seed in candidates.items():
            if name == "all" and seed["rows"] == candidates["top8"]["rows"]:
                attempts[name] = dict(reused_from="top8", fits=attempts["top8"]["fits"])
                continue

            def factory(*args):
                return transfer_problem(*args, pairs=fixed_pairs, mode=mode)

            fits = fit_once(scan, seed, method, best["c0"]["east_north_km"], problem_class=factory)
            check_pair(fits)
            attempts[name] = dict(fits=fits)
        choices = dict(incumbent=best, **{name: a["fits"] for name, a in attempts.items()})
        selected = min(choices, key=lambda k: choices[k]["c0"]["score"])
        old_score = best["c0"]["score"]
        best = choices[selected]
        record = dict(
            iteration=iteration,
            diagnostics=diagnostics,
            attempts=attempts,
            selected=selected,
            selected_fits=best,
            objective_improvement=float(old_score - best["c0"]["score"]),
        )
        records.append(record)
        write(path, records)
        write(
            directory / "selected.json",
            dict(fits=best, selected_round=iteration, initial_source=str(original)),
        )
        print(
            json.dumps(
                dict(
                    case=case,
                    iteration=iteration,
                    selected=selected,
                    improvement=record["objective_improvement"],
                    changed_groups=diagnostics["changed_groups"],
                    positions={a: list(f["east_north_km"]) for a, f in best.items()},
                )
            ),
            flush=True,
        )
        if selected == "incumbent":
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    run(a.case)
