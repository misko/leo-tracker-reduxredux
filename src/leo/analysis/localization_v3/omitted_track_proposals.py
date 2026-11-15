"""Bounded nominations of native tracks outside the initial curved population.

The fitted incumbent supplies receiver correction and a position in each arm.
Target points never update that incumbent. These full-data scores choose only
which tracks may receive independent annotation, inclusion and exact audit.
"""

from copy import deepcopy

import numpy as np

from leo.analysis.localization_v3.screen_geometry import phase_frequency_grids
from leo.analysis.research.orbit_phase_geometry import FrozenOrbitBank
from leo.analysis.research.track_recovery_diagnostics import profile_rate

ARMS = ("c0", "fitted_c")
POLICY = "omitted_uncurved_calibrated_v1"
PHASES = tuple(float(p) for p in range(-15, 16, 3))


def _eligible(context, evidence):
    scan, owners = context["scan"], evidence["owners"]
    if set(context["problems"]) != set(ARMS) or set(owners) != set(ARMS):
        raise ValueError("Both calibrated problems and ownership maps required")
    grouped = {a: {} for a in ARMS}
    for row in evidence["inventory"]["tracks"]:
        arm, tid = row["arm"], row["track_id"]
        if arm not in grouped or tid in grouped[arm]:
            raise ValueError("Unique paired native inventory required")
        grouped[arm][tid] = row
    occupied = set().union(*(set(owners[a]) for a in ARMS))
    candidates, excluded = [], []
    for tid in sorted(grouped["c0"]):
        row, other = grouped["c0"][tid], grouped["fitted_c"].get(tid)
        if other is None or not all(r["current_large"] for r in (row, other)):
            continue
        i = row["track_index"]
        if i != other["track_index"] or not 0 <= i < len(scan.tracks):
            raise ValueError("Paired inventory track index differs")
        track = scan.tracks[i]
        ids = set(track["observation_ids"])
        if any(r["component"] != track["key"] for r in (row, other)):
            raise ValueError("Paired inventory component differs from native track")
        if i in scan.curved:
            excluded.append(dict(track_id=tid, reason="initial_curved_population"))
            continue
        if any(set(r["all_track_observation_ids"]) != ids for r in (row, other)):
            raise ValueError("Paired inventory parent differs from native track")
        if any(set(r["observation_ids"]) != ids for r in (row, other)) or ids & occupied:
            excluded.append(dict(track_id=tid, reason="not_wholly_unowned_in_both_arms"))
            continue
        times, values = np.asarray(track["times"], float), np.asarray(track["values"], float)
        if (times.ndim != 1 or values.shape != times.shape or len(times) != len(ids)
                or not np.isfinite(times).all() or not np.isfinite(values).all()
                or np.any(np.diff(times) <= 0)):
            raise ValueError("Unique ordered finite native track points required")
        if len(times) < 20 or np.ptp(times) < 20:
            raise ValueError("Large inventory target lacks native point or duration support")
        if any(i in p.members and p.keep[p.slices[p.members.index(i)]].any()
               for p, _ in context["problems"].values()):
            raise ValueError("Omitted target already calibrates the incumbent")
        pick = np.unique(np.linspace(0, len(times) - 1, min(16, len(times))).astype(int))
        candidates.append(dict(target=dict(deepcopy(row), inactive_fragment=False), indices=pick))
    return candidates, excluded


def rank_omitted_tracks(context, evidence, *, max_proposals=2):
    """Return one common order for at most two independent recovery attempts.

    ``evidence`` is the wrapper returned by ``prepare_recovery``. Selection is
    independent of its old top-eight order and target-limit prefix. The full
    catalogue and eleven phase values are identical in both calibration arms.
    Later annotation must regenerate labels and aliases from its training data.
    No nominated label or score is copied into the returned recovery targets.
    """
    if type(max_proposals) is not int or not 1 <= max_proposals <= 2:
        raise ValueError("Omitted-track proposal cap must be one or two")
    candidates, excluded = _eligible(context, evidence)
    scan = context["scan"]
    protocol = dict(
        max_proposals=max_proposals,
        maximum_points_per_track=16,
        phase_grid_s=list(PHASES),
        phase_grid_penalty=False,
        rate_prior_sigma_hz_s=0.5,
        bias_prior_sigma_hz=300.0,
        noise_hz=150.0,
        maximum_nomination_rms_hz=450.0,
        maximum_nomination_bias_hz=3000.0,
        ranking="maximum_arm_cost_per_sample_then_decreasing_native_points_then_track_id",
        paired_candidate_sets=True,
        paired_priors_and_search_budgets=True,
        full_data_track_nomination=True,
        target_used_for_calibration=False,
        target_label_or_alias_supplied_to_annotation=False,
        independent_annotation_inclusion_and_audit_required=True,
        position_inclusion_authorized=False,
        GPS_used=False,
        future_TLE_used=False,
    )
    result = dict(policy=POLICY, protocol=protocol, targets=[], rows=[], excluded=excluded,
                  eligible_targets=len(candidates), no_GPS_inference=True, causal_only=True)
    if not candidates:
        return result
    query = np.unique(np.concatenate([
        scan.tracks[c["target"]["track_index"]]["times"][c["indices"]] for c in candidates
    ]))
    protocol["unique_query_times"] = len(query)
    knots = np.asarray(scan.sky["time_s"], float)
    all_times = np.concatenate([
        scan.tracks[c["target"]["track_index"]]["times"] for c in candidates
    ])
    if all_times.min() + min(PHASES) < knots[0] or all_times.max() + max(PHASES) > knots[-1]:
        raise ValueError("Full omitted track phase domain leaves the causal orbit bank")
    bank = FrozenOrbitBank(scan.sky)
    states = {a: p.state(x) for a, (p, x) in context["problems"].items()}
    positions = [scan.search_region.latlon(context["problems"][a][1]) for a in ARMS]
    count = len(scan.norads)
    protocol["catalogue_candidates"] = count
    for candidate in candidates:
        i = candidate["target"]["track_index"]
        track, pick = scan.tracks[i], candidate["indices"]
        candidate["columns"] = np.searchsorted(query, track["times"][pick])
        candidate["corrected"] = {}
        candidate["best"] = {}
        for arm in ARMS:
            state = states[arm]
            corrected = (track["values"] - scan.hardware(track, state["beta"])
                         - track["rf_hz"] / 11.5e9
                         * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1])
            candidate["corrected"][arm] = corrected[pick]
            candidate["best"][arm] = {}
    for phase in PHASES:
        grids = phase_frequency_grids(bank, query, positions, phase_seconds=phase)
        for candidate in candidates:
            i = candidate["target"]["track_index"]
            track, pick, columns = scan.tracks[i], candidate["indices"], candidate["columns"]
            for arm, (frequency, elevation) in zip(ARMS, grids, strict=True):
                score = profile_rate(
                    candidate["corrected"][arm], track["rf_hz"] / 11.5e9 * frequency[:, columns],
                    track["times"][pick], rate_sigma_hz_s=0.5, bias_sigma_hz=300.0)
                cost = score["cost"]
                possible = ((elevation[:, columns].min(axis=1) >= 0)
                            & (score["rms_hz"] <= 450.0) & (abs(score["bias_hz"]) <= 3000.0))
                for alias in np.unique(score["alias"][possible]).astype(int):
                    by_alias = candidate["best"][arm]
                    if alias not in by_alias:
                        by_alias[alias] = dict(
                            cost=np.full(count, np.inf), rms_hz=np.zeros(count),
                            bias_hz=np.zeros(count), phase_s=np.zeros(count))
                    best = by_alias[alias]
                    better = possible & (score["alias"] == alias) & (cost < best["cost"])
                    best["cost"][better] = cost[better]
                    best["phase_s"][better] = phase
                    for key in ("rms_hz", "bias_hz"):
                        best[key][better] = score[key][better]
    ranked = []
    for candidate in candidates:
        target, by_arm = candidate["target"], candidate["best"]
        score, aliases = np.full(count, np.inf), np.zeros(count, int)
        for alias in sorted(by_arm["c0"].keys() & by_arm["fitted_c"].keys()):
            value = np.maximum(*(by_arm[a][alias]["cost"] for a in ARMS))
            value /= len(candidate["indices"])
            better = value < score
            score[better], aliases[better] = value[better], alias
        possible = np.flatnonzero(np.isfinite(score))
        row = dict(track_id=target["track_id"], component=target["component"],
                   points=len(target["observation_ids"]),
                   nomination_local_indices=candidate["indices"].tolist(),
                   common_candidates=int(len(possible)),
                   status="no_common_plausible_candidate", selected=False)
        if len(possible):
            j = min(possible, key=lambda k: (score[k], int(scan.norads[k])))
            alias = int(aliases[j])
            row.update(status="ranked", nomination_norad=int(scan.norads[j]),
                       nomination_candidate_index=int(j), nomination_alias=alias,
                       maximum_arm_cost_per_sample=float(score[j]),
                       arms={a: {k: float(v[j]) for k, v in by_arm[a][alias].items()}
                             for a in ARMS})
            ranked.append((row["maximum_arm_cost_per_sample"], -row["points"],
                           row["track_id"], target, row))
        result["rows"].append(row)
    ranked.sort(key=lambda r: r[:3])
    for rank, (_, _, _, target, row) in enumerate(ranked, 1):
        row["rank"] = rank
        if rank <= max_proposals:
            row["selected"] = True
            result["targets"].append(target)
    return result
