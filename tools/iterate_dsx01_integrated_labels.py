"""Candidate proposals reranked by the complete robust integrated objective.

Timing-linked source groups, curved point inventory and candidate banks stay
fixed. This is a heuristic alternating search, not a proof of exact EM.
"""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import run_dsx01_joint_marginal as engine
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_robust_joint import RobustJoint
from iterate_dsx01_clock_identities import fixed_pair_inventory, grouped_labels
from iterate_dsx01_profiled_identity import explore
from prototype_dsx01_continuous_position import latlon, native_point, numpy_state
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import measurement_path, read_pairs

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD

OUTPUT = engine.ROOT / "reports/2026_10_18_dsx01_integrated_labels"


def accept_pair(incumbent, proposal, *, minimum_gain=1.0):
    gain = incumbent["c0"]["score"] - proposal["c0"]["score"]
    return (proposal, float(gain)) if gain >= minimum_gain else (incumbent, 0.0)


def changed_seed(incumbent, changes, phases, norads):
    """Apply complete group proposals without mutating the fitted incumbent."""
    seed = dict(rows=deepcopy(incumbent["rows"]), state=numpy_state(incumbent["state"]))
    owners = {r["candidate_index"] for r in seed["rows"]}
    for change in changes:
        j = change["new"]
        for k in change["group"]:
            seed["rows"][k].update(candidate_index=int(j), candidate_norad=int(norads[j]))
        if j not in owners:
            seed["state"]["phases"][j] = phases[j]
    return seed


def proposal_candidates(scan, incumbent, groups):
    anchor, state = incumbent["east_north_km"], numpy_state(incumbent["state"])
    proposal, diagnostics = explore(scan, state, anchor, "receiver_smooth", compact_update=False)
    base = phase_linear_frequency(scan.geometry, *latlon(anchor))
    _, _, nominees, prediction = scan.association(
        proposal["state"], base, native_point(scan, anchor), "receiver_smooth"
    )
    by_component = {track["key"]: i for i, track in enumerate(scan.tracks)}
    costs = []
    for row in incumbent["rows"]:
        i = by_component[row["component"]]
        terms = nominees[i]["terms"]
        n = len(scan.tracks[i]["times"])
        cost = (n + 4) * np.log1p(np.maximum(0.0, terms["cost"]) / 4)
        visible = prediction[1][:, scan.index[i]].min(axis=1) >= 0
        costs.append(np.where(visible, cost, np.inf))
    costs = np.array(costs)
    prior = (proposal["state"]["phases"] / np.maximum(1.0, scan.sky["phase_sigma_s"])) ** 2
    for group in groups:
        costs[group] += prior / len(group)
    changes = grouped_labels(costs, groups, [r["candidate_index"] for r in incumbent["rows"]])
    ordered = sorted(
        (r for r in changes if r["new"] != r["old"] and r["gain"] > 0), key=lambda r: -r["gain"]
    )[:8]
    ordered = [dict(r, gain=r["gain"] if np.isfinite(r["gain"]) else None) for r in ordered]
    candidates = {f"group{k}": [change] for k, change in enumerate(ordered)}
    if len(ordered) > 1:
        candidates["all"] = ordered
    return {
        name: (changed_seed(incumbent, changes, proposal["state"]["phases"], scan.norads), changes)
        for name, changes in candidates.items()
    }, diagnostics


def candidate_aliases(scan, incumbent, seed, changes, sigma):
    p = RobustJoint(scan, seed, False, variant="robust", sigma=sigma, aliases=incumbent["aliases"])
    frequency, _ = paired_phase_frequency(
        p.sky, p.flat_times, p.flat_labels, p.reference, *latlon(incumbent["east_north_km"])
    )
    aliases = list(incumbent["aliases"])
    for k in {k for change in changes for k in change["group"]}:
        t, sl = scan.tracks[p.members[k]], p.slices[k]
        raw = t["values"] - scan.hardware(t, seed["state"]["beta"])
        raw = (
            raw
            - p.q[sl] * frequency[sl]
            - p.q[sl] * (scan.rx_basis[p.members[k]] @ seed["state"]["smooth"][t["receiver"] - 1])
        )
        aliases[k] = int(np.rint(-np.mean(raw) / PERIOD))
    return aliases


def run(case, *, rounds=2):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    original = engine.OUTPUT / case / "robust/endpoints.json"
    initial = json.loads(original.read_text())["fits"]
    scan = Scan(case)
    apply_measurements(scan, json.loads(measurement_path(case).read_text())["points"], "glrt300")
    _, groups = fixed_pair_inventory(scan, initial["c0"], read_pairs(case)[0])
    sigma = initial["c0"]["diagnostics"]["noise_sigma_hz"]
    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_TLE_input=True,
            source=str(original),
            source_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            curved_groups=groups,
            groups_and_all_original_observations_frozen=True,
            maximum_rounds=rounds,
            maximum_changed_groups=8,
            unary_proposals_only_rank_full_integrated_c0_cost=True,
            at_most_one_joint_refit_per_round=True,
            Mstep="25-km grid, 3 c0-selected starts, 24 iterations, 3 phase rounds, matched c arms",
            minimum_objective_gain=1.0,
            c0_selection_keeps_exact_fitted_c_partner=True,
            aliases_recomputed_only_for_relabelled_curves_at_blind_anchor=True,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    path = directory / "rounds.json"
    records = json.loads(path.read_text()) if path.exists() else []
    best = records[-1]["selected_fits"] if records else initial
    for iteration in range(len(records), rounds):
        incumbent = best["c0"]
        candidates, diagnostics = proposal_candidates(scan, incumbent, groups)
        ranked = {}
        for name, (seed, changes) in candidates.items():
            aliases = candidate_aliases(scan, incumbent, seed, changes, sigma)
            p = RobustJoint(scan, seed, False, variant="robust", sigma=sigma, aliases=aliases)
            z = p.residual(np.array(incumbent["east_north_km"]))
            ranked[name] = dict(
                seed=seed, changes=changes, aliases=aliases, full_c0_anchor_cost=float(z @ z)
            )
        selected_name = (
            min(ranked, key=lambda k: ranked[k]["full_c0_anchor_cost"]) if ranked else None
        )
        attempt, gain = None, 0.0
        if selected_name is not None:
            item = ranked[selected_name]
            proposed = dict(
                incumbent,
                state=item["seed"]["state"],
                rows=item["seed"]["rows"],
                aliases=item["aliases"],
                proposed_seed_only_not_completed_fit=True,
            )
            source = dict(c0=proposed, fitted_c=best["fitted_c"])
            seed_path = directory / f"round{iteration}_seed.json"
            write(seed_path, source)
            source = json.loads(seed_path.read_text())
            engine.OUTPUT = OUTPUT / "msteps" / f"round{iteration}"
            engine.JointMarginal = RobustJoint
            engine.incumbents = lambda *args, source=source: {"proposed": source}
            engine.run(case, variants=("robust",))
            result_path = engine.OUTPUT / case / "robust/endpoints.json"
            attempt = json.loads(result_path.read_text())["fits"]
            best, gain = accept_pair(best, attempt)
        record = dict(
            iteration=iteration,
            proposal_diagnostics=diagnostics,
            ranked=ranked,
            selected_candidate=selected_name,
            attempted_fits=attempt,
            objective_improvement=gain,
            selected_fits=best,
        )
        records.append(record)
        write(path, records)
        write(directory / "selected.json", dict(fits=best, selected_round=iteration))
        print(
            json.dumps(
                dict(
                    case=case,
                    iteration=iteration,
                    candidates=len(ranked),
                    selected_candidate=selected_name,
                    gain=gain,
                    retained_incumbent=gain == 0,
                )
            ),
            flush=True,
        )
        if gain == 0:
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    args = parser.parse_args()
    run(args.case)
