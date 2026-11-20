"""Readmit whole curved tracks using component-excluded receiver calibration."""

import json
import sys
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import bridge_cavity, orbit_projector, v5_lean

METHOD = "bridge_support"
BOUNDARY = "Complete stored native GLRT through one component-excluded paired v5 reclassification"
SHORTLIST = 4


def pick_candidate(candidates, costs, passing, incumbent, supported):
    """Apply one held score to all candidates and keep an incumbent on a tie."""
    previous = np.flatnonzero(candidates == incumbent)
    old = int(previous[0]) if len(previous) else None
    if supported and old is None:
        return None
    eligible = np.flatnonzero(passing)
    if not len(eligible):
        return old if supported else None
    best = int(eligible[np.argmin(costs[eligible])])
    if supported and old is not None and costs[old] <= costs[best]:
        return old
    return best


def held_choice(scan, track_index, state, anchor, grid, incumbent, supported):
    from leo.analysis.localization_v3 import discovery
    from leo.analysis.localization_v3.family_weighting import candidate_profile

    t, ix = scan.tracks[track_index], scan.index[track_index]
    q = t["rf_hz"] / 11.5e9
    observed = t["values"] - scan.hardware(t, state["beta"])
    observed -= q * scan.rx_basis[track_index] @ state["smooth"][t["receiver"] - 1]
    frequency, elevation, slope = grid
    visible = np.flatnonzero(elevation[:, ix].min(axis=1) >= 0)
    if not len(visible):
        return None
    design = q * frequency[np.ix_(visible, ix)]
    derivatives = q * slope[np.ix_(visible, ix)]
    profile = candidate_profile(
        observed,
        design,
        derivatives,
        elevation[np.ix_(visible, ix)],
        scan.radio_sigma_hz,
        scan.sigma[visible],
    )
    short = np.argsort(profile["cost"], kind="stable")[:SHORTLIST]
    old = np.flatnonzero(visible == incumbent)
    if len(old) and old[0] not in short:
        short = np.r_[short, old]
    candidates = visible[short]
    phases = profile["phase_s"][short]
    sky = {
        "time_s": scan.sky["time_s"],
        "position_km": scan.sky["position_km"][candidates],
        "velocity_km_s": scan.sky["velocity_km_s"][candidates],
    }
    geo = orbit_projector.prepare(sky, t["times"], phases)
    shifted, elevations, _ = discovery.phase_linear_frequency(
        geo, *scan.search_region.latlon(anchor)
    )
    terms = scan.curve(track_index, observed, q * shifted, "receiver_smooth")
    costs = terms["cost"] + (phases / scan.sigma[candidates]) ** 2
    passing = (
        terms["passing"]
        & (elevations.min(axis=1) >= 0)
        & (terms["alias"] == profile["aliases"][short])
    )
    choice = pick_candidate(candidates, costs, passing, incumbent, supported)
    if choice is None:
        return None
    j = int(candidates[choice])
    previous = np.flatnonzero(candidates == incumbent)
    return (
        j,
        int(terms["alias"][choice]),
        float(phases[choice]),
        float(terms["rms"][choice]),
        float(costs[previous[0]] - costs[choice]) if len(previous) else None,
    )


def reclassify(scan, original, provisional, metrics):
    from leo.analysis.localization_v3 import discovery
    from leo.analysis.localization_v3.marginal import JointMarginal
    from leo.analysis.localization_v3.position import NormalPosition

    select, branches = original(scan, provisional)
    began = perf_counter()
    winner = select["choices"][0]
    before = winner["node"]
    accepted = {
        r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"] if r["compatible"]
    }
    if not accepted:
        return select, branches

    tracks = {scan.tracks[i]["key"]: i for i in scan.curved}
    rows = before["seed"]["rows"]
    bootstrap = np.concatenate(
        [
            np.full(len(scan.tracks[tracks[r["component"]]]["times"]), r["component"] in accepted)
            for r in rows
        ]
    )
    bootstrap_points = int(bootstrap.sum())
    anchor = np.asarray(provisional["start_xy"])
    p = NormalPosition(scan, before, scan.radio_sigma_hz, False, keep=bootstrap)
    geometry = JointMarginal.calculate(p, anchor, geometry_only=True)
    design, raw = geometry["features"], p.values - p.q * geometry["intercept"]

    def receiver_state(train):
        # NormalPosition's original posterior and decoder, with fixed geometry.
        result = scan.bound(raw[train], design[train], p.point_noise[train], p.noise_groups[train])
        with patch.object(p, "calculate", return_value=dict(geometry, **result)):
            return discovery.reference_state(p.state(anchor))

    state = receiver_state(bootstrap)
    bank = discovery.phase_linear_frequency(scan.geometry, *scan.search_region.latlon(anchor))
    phases, changed, added, scored = {}, [], [], []
    node_rows, node_aliases, node_gates = [], [], []
    for row, alias, index, section in zip(p.rows, p.alias, p.members, p.slices, strict=True):
        key, j = row["component"], row["candidate_index"]
        selected = key in accepted
        independent = state
        points = int(section.stop - section.start)
        if selected and bootstrap_points > points:
            train = bootstrap.copy()
            train[section] = False
            independent = receiver_state(train)
        choice = (
            None
            if selected and bootstrap_points == points
            else held_choice(scan, index, independent, anchor, bank, j, selected)
        )
        if choice is not None:
            new_j, new_alias, phase, rms, gain = choice
            if not selected or new_j != j:
                event = dict(
                    component=key,
                    old_norad=int(scan.norads[j]),
                    norad=int(scan.norads[new_j]),
                    points=points,
                    held_rms_hz=rms,
                    held_gain=gain,
                )
                (changed if selected else added).append(event)
                alias = new_alias
            j = new_j
            phases.setdefault(j, []).append(phase)
            scored.append(key)
        node_rows.append(dict(row, candidate_index=j, candidate_norad=int(scan.norads[j])))
        node_aliases.append(alias)
        node_gates.append(dict(component=key, compatible=selected or choice is not None))
    for j, values in phases.items():
        state["phases"][j] = np.median(values)
    winner["node"] = dict(seed=dict(state=state, rows=node_rows), aliases=node_aliases)
    winner["arms"]["c0"]["metrics"]["tracks"] = node_gates
    metrics.update(
        curved_tracks=len(rows),
        scored_tracks=len(scored),
        bootstrap_tracks=len(accepted),
        bootstrap_points=bootstrap_points,
        readmitted=added,
        reassigned=changed,
        reclassification_s=perf_counter() - began,
    )
    return select, branches


def support(arms):
    return {
        arm: dict(
            curved=[
                dict(component=row["component"], norad=int(row["norad"]), points=int(row["points"]))
                for row in rows["gates"]["tracks"]
                if row["compatible"]
            ],
            predictive_points=int(rows.get("predictive_points", 0)),
        )
        for arm, rows in arms.items()
    }


def worker(request, target, library, mode="candidate"):
    from leo.analysis.localization_v3 import family_cavity

    initialize = bridge_cavity.initialize
    nominate, cavity = family_cavity.nominate_families, family_cavity.cavity_policy
    support_metrics = {}

    def select(scan, metrics):
        return reclassify(scan, initialize, metrics, support_metrics)

    def nominations(context):
        support_metrics["final_support"] = support(context["arms"])
        return nominate(context)

    def complete(context, proposed):
        output = cavity(context, proposed)
        if output["status"] == "complete":
            support_metrics["final_support"] = support(output["policy_arms"])
            support_metrics["cavity_replacements"] = (
                output["selected"]["replacements"] if output["selected"] else []
            )
        return output

    with ExitStack() as stack:
        if mode == "candidate":
            stack.enter_context(patch.object(bridge_cavity, "initialize", select))
        elif mode != "prior":
            raise ValueError("unknown bridge replay mode")
        stack.enter_context(patch.object(family_cavity, "nominate_families", nominations))
        stack.enter_context(patch.object(family_cavity, "cavity_policy", complete))
        bridge_cavity.worker(request, target, library)
    target = Path(target)
    result = json.loads(target.read_bytes())
    result["boundary"] = BOUNDARY if mode == "candidate" else bridge_cavity.BOUNDARY
    result["metrics"]["bridge_support"] = support_metrics
    save_json(target, result)


def run(case, work_dir, mode="candidate"):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(
        case, directory, Path(__file__), worker_args=(str(library), mode)
    )


if __name__ == "__main__":
    worker(*sys.argv[1:])
