"""Complete-family cavity nominations and matched full-evidence replacement fits.

Inputs are the current scan's owned signed context. No storage, old workers,
completed results or evaluation coordinates are read by these numerical policies.
"""

import copy

import numpy as np

from leo.analysis.localization_v3.cavity_prediction import (
    coarse_phase_scores,
    gaussian_prediction,
    legacy_phase_reference,
    unused_student_gap,
)
from leo.analysis.localization_v3.event_position import (
    attach_event_predictive,
    make_event_problem,
    refit,
)
from leo.analysis.localization_v3.feasible import constrained, gate_slacks
from leo.analysis.localization_v3.history_policy import ARMS, pair_passes
from leo.analysis.localization_v3.orbit_modes import build_modes
from leo.analysis.localization_v3.predictive_linear import geometry_features, linear_geometry
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes


def valid(pair, *, half_width_km=12.5):
    if not pair_passes(pair, include_linear=True, half_width_km=half_width_km):
        return False
    return all(np.max(np.abs(np.asarray(r['state']['phases']))) <= 15.000001
               for r in pair.values())


def adopt_equal_assignment_prior(result):
    """Original production adoption, retaining the historical sticky control."""
    if result['status'] != 'complete' or result.get('reconstructed_fresh_reference'):
        return result
    eligible = [t for t in result['trials'] if t['paired_valid']]
    best = (min(eligible, key=lambda t: t['arms']['c0']['corrected_selection_loss'])
            if eligible else None)
    accepted = bool(best and best['arms']['c0']['corrected_selection_loss'] <
                    result['baseline_corrected_loss']['c0'])
    return dict(result, sticky_control_accepted=result['accepted'],
        sticky_control_policy_arms=result['policy_arms'], accepted=accepted,
        selected=best if accepted else None,
        policy_arms=best['arms'] if accepted else result['baseline_arms'],
        adoption='equal_assignment_priors_minimum_corrected_normalized_c0',
        reconstructed_fresh_reference=True)


def cavity_policy(context, nominations):
    if nominations['status'] != 'complete':
        return nominations
    return adopt_equal_assignment_prior(fit_cavity_proposals(context, nominations))


def family_data(d, target):
    base = d["base"]
    keep = d["keep"].copy()
    curved = []
    for k, (row, _i, sl) in enumerate(zip(base.rows, base.members, base.slices, strict=True)):
        if row["candidate_index"] == target:
            keep[sl] = False
            if d["keep"][sl].any():
                curved.append(k)
    reference = d["reference"].copy()
    for _ in range(5):
        p = make_event_problem(
            d["scan"], d["node"], keep, "c0", reference, d["powers"], d["means"], d["model"], []
        )
        phase = np.clip(p.state(d["x"])["phases"][p.labels], -15, 15)
        phase_change = float(np.max(abs(phase - reference)))
        reference = phase
    if phase_change > 0.01:
        raise ValueError("family-excluded calibration phase did not converge")
    c = p.calculate(d["x"])
    present = p.noise_groups[keep]
    u = c["features"][keep]
    w = d["powers"][present] * c["noise_precision"][present] / p.point_noise[keep] ** 2
    gram = np.diag(c["coefficient_prior_precision"]) + u.T @ (u * w[:, None])
    cov = np.linalg.inv(gram)
    radio_width = p.hardware.shape[1] + p.smooth.shape[1]
    times = []
    values = []
    q = []
    radio = []
    noise = []
    groups = []
    members = []
    for k in curved:
        i = base.members[k]
        sl = base.slices[k]
        use = d["keep"][sl]
        t = p.scan.tracks[i]
        g = len(members)
        members.append(
            dict(
                kind="curved",
                row_index=k,
                component=t["key"],
                track_index=i,
                points=int(use.sum()),
                observation_ids=np.asarray(t["observation_ids"])[use].tolist(),
                receiver=t["receiver"],
                channel=t["channel"],
            )
        )
        times.extend(t["times"][use])
        values.extend(t["values"][use])
        q.extend(p.q[sl][use])
        radio.extend(c["features"][sl, :radio_width][use])
        noise.extend(p.point_noise[sl][use] * np.sqrt(2 / d["powers"][k]))
        groups.extend([g] * int(use.sum()))
    selected = [e for e in d["entries"] if e["candidate_index"] == target]
    if selected:
        view, y, sigma, g, slices = linear_geometry(p, selected)
        geometry = geometry_features(view, d["x"], 0.0)
        for entry, sl in zip(selected, slices, strict=True):
            t = p.scan.tracks[entry["track_index"]]
            if t["observation_ids"] != entry["observation_ids"]:
                raise ValueError("predictive metadata differs from held numerical rows")
            group = len(members)
            members.append(
                dict(
                    kind="predictive",
                    component=entry["component"],
                    track_index=entry["track_index"],
                    points=len(t["times"]),
                    observation_ids=t["observation_ids"],
                    receiver=t["receiver"],
                    channel=t["channel"],
                )
            )
            times.extend(t["times"])
            values.extend(t["values"])
            q.extend(view.q[sl])
            radio.extend(geometry["features"][sl, :radio_width])
            noise.extend(sigma[sl] * np.sqrt(2))
            groups.extend([group] * len(t["times"]))
    times, values, q, radio, noise, groups = map(
        np.asarray, (times, values, q, radio, noise, groups)
    )
    calibration_ids = {
        oid
        for i, sl in zip(p.members, p.slices, strict=True)
        for oid, use in zip(p.scan.tracks[i]["observation_ids"], keep[sl], strict=True)
        if use
    }
    held_ids = {oid for m in members for oid in m["observation_ids"]}
    if calibration_ids & held_ids:
        raise ValueError("held family was used in calibration")
    covariance = (
        np.diag(noise**2)
        + radio @ cov[:radio_width, :radio_width] @ radio.T
        + 300.0**2 * (groups[:, None] == groups[None, :])
    )
    return dict(
        p=p,
        coefficient=c["coefficient"],
        covariance=cov,
        radio_width=radio_width,
        times=times,
        values=values,
        q=q,
        radio=radio,
        noise=noise,
        groups=groups,
        members=members,
        base_covariance=covariance,
        calibration_mask=keep,
        held_ids=sorted(held_ids),
        cavity_phase_change_s=phase_change,
        held_owners=len({(m["receiver"], m["channel"]) for m in members if m["kind"] == "curved"}),
    )


def candidate_prediction(d, data, j, aliases):
    p = data["p"]
    nb = data["radio_width"]
    old_active = {
        r["candidate_index"] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()
    }
    supported = j in p.supported or data["held_owners"] >= 2
    if j in p.supported:
        k = p.labels.index(j)
        mode_bank = dict(
            time_s=p.mode_bank["time_s"],
            position_km=p.mode_bank["position_km"][3 * k : 3 * k + 3],
            velocity_km_s=p.mode_bank["velocity_km_s"][3 * k : 3 * k + 3],
        )
    else:
        mode_bank = build_modes(d["scan"], [j], [j] if supported else [], "physical")[0]
    bank = dict(
        time_s=d["scan"].sky["time_s"],
        position_km=d["scan"].sky["position_km"][[j]],
        velocity_km_s=d["scan"].sky["velocity_km_s"][[j]],
    )
    slots = list(range(nb))
    mean = data["coefficient"][:nb].tolist()
    phase_slot = nb + p.labels.index(j) if j in p.labels and j in old_active else None
    slots.append(phase_slot)
    mean.append(
        data["coefficient"][phase_slot]
        if phase_slot is not None
        else d["all_means"][j] / d["widths"][j]
    )
    if supported:
        start = (
            nb + len(p.labels) + 3 * p.supported.index(j)
            if j in p.supported and j in old_active
            else None
        )
        slots.extend([start + k if start is not None else None for k in range(3)])
        mean.extend(data["coefficient"][start : start + 3] if start is not None else np.zeros(3))
    nconstant = len(data["members"])
    slots.extend([None] * nconstant)
    mean.extend(np.zeros(nconstant))
    mean = np.asarray(mean)
    covariance = np.eye(len(slots))
    used = [k for k, s in enumerate(slots) if s is not None]
    old = [slots[k] for k in used]
    covariance[np.ix_(used, used)] = data["covariance"][np.ix_(old, old)]
    covariance[-nconstant:, -nconstant:] = np.eye(nconstant) * 300**2
    constants = np.eye(nconstant)[data["groups"]]
    reference = float(mean[nb] * d["widths"][j])
    history = []
    values = data["values"] + np.asarray(aliases)[data["groups"]] / 4.4e-06

    def geometry(phase):
        f, e = phase_frequency_grid(
            bank, data["times"], *d["scan"].search_region.latlon(d["x"]), phase_seconds=phase
        )
        plus, _ = phase_frequency_grid(
            bank, data["times"], *d["scan"].search_region.latlon(d["x"]), phase_seconds=phase + 0.01
        )
        minus, _ = phase_frequency_grid(
            bank, data["times"], *d["scan"].search_region.latlon(d["x"]), phase_seconds=phase - 0.01
        )
        derivative = (plus[0] - minus[0]) / 0.02
        intercept = data["q"] * (f[0] - derivative * phase)
        features = [data["radio"], (data["q"] * derivative * d["widths"][j])[:, None]]
        if supported:
            modes = paired_frequency_modes(
                bank,
                mode_bank,
                data["times"],
                np.zeros(len(data["times"]), int),
                np.array([phase]),
                *d["scan"].search_region.latlon(d["x"]),
            )
            features.append(data["q"][:, None] * modes)
        return (intercept, np.column_stack((*features, constants)), e[0])

    for _ in range(5):
        intercept, features, e = geometry(reference)
        result = gaussian_prediction(
            values - intercept - features @ mean, features, covariance, data["noise"]
        )
        coefficient = mean + result["parameter_update"]
        phase = float(coefficient[nb] * d["widths"][j])
        change = abs(phase - reference)
        history.append(change)
        reference = float(np.clip(phase, -15, 15))
    if abs(phase) <= 15:
        intercept, features, e = geometry(phase)
        residual = values - intercept - features @ coefficient
    else:
        e = np.full(len(values), -90.0)
        residual = result["native_residual"]
    return dict(
        candidate_index=j,
        norad=int(d["scan"].norads[j]),
        score=result["objective"],
        phase_s=phase,
        phase_change_s=change,
        minimum_elevation_deg=float(e.min()),
        aliases=aliases,
        conditional_RMS_hz=float(np.sqrt(np.mean(residual**2))),
        qualified=bool(abs(phase) <= 15 and e.min() >= 0 and (change <= 0.01)),
        residual_hz=residual,
        coefficient=coefficient,
        prior_mean=mean,
        prior_covariance=covariance,
        calibration_slots=slots,
        physical_modes=supported,
        all_held_observations_predictive_never_calibrate=True,
    )


def unused_count(p, entries):
    active = {
        r["candidate_index"] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()
    }
    active.update(e["candidate_index"] for e in entries)
    return len(set(p.labels) - active)


def configuration(d, offers):
    node = copy.deepcopy(d["node"])
    entries = copy.deepcopy(d["entries"])
    scan = d["scan"]
    changes = {}
    for family, offer in offers:
        target = family["original_index"]
        candidate = offer["candidate_index"]
        lookup = {
            m["component"]: int(a) for m, a in zip(family["members"], offer["aliases"], strict=True)
        }
        if target in changes:
            raise ValueError("each original family can be replaced only once")
        changes[target] = (candidate, lookup)
    for k, (original, row) in enumerate(
        zip(d["node"]["seed"]["rows"], node["seed"]["rows"], strict=True)
    ):
        if original["candidate_index"] in changes:
            candidate, lookup = changes[original["candidate_index"]]
            row.update(candidate_index=candidate, candidate_norad=int(scan.norads[candidate]))
            if row["component"] in lookup:
                node["aliases"][k] = lookup[row["component"]]
    for original, entry in zip(d["entries"], entries, strict=True):
        if original["candidate_index"] in changes:
            candidate, lookup = changes[original["candidate_index"]]
            entry.update(
                candidate_index=candidate,
                norad=int(scan.norads[candidate]),
                alias=lookup[entry["component"]],
            )
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    if set(e["candidate_index"] for e in entries) - set(labels):
        raise ValueError("predictive candidate lacks original model coordinate")
    return (node, entries, d["all_means"][labels])


def fit_configuration(d, node, entries, means):
    """Fit an explicit research hypothesis under the unchanged final model."""
    pair = {
        arm: refit(d["scan"], node, d["keep"], arm, d["powers"], means, d["model"], [], entries)
        for arm in ARMS
    }
    attempted = False
    if not valid(pair, half_width_km=d['scan'].search_region.half_width_km):
        minima = []
        for arm in ARMS:
            r = pair[arm]
            p = make_event_problem(
                d["scan"],
                node,
                d["keep"],
                arm,
                np.asarray(r["phase_reference"]),
                d["powers"],
                means,
                d["model"],
                [],
            )
            attach_event_predictive(p, entries, d["powers"])
            minima.append(
                min(gate_slacks(p, np.asarray(r["endpoint_east_north_km"]), entries).values())
            )
        if min(minima) >= -0.25:
            pair = constrained(
                d["scan"], node, d["keep"], d["powers"], means, d["model"], entries, pair
            )
            attempted = True
    for arm, r in pair.items():
        p = make_event_problem(
            d["scan"],
            node,
            d["keep"],
            arm,
            np.asarray(r["phase_reference"]),
            d["powers"],
            means,
            d["model"],
            [],
        )
        attach_event_predictive(p, entries, d["powers"])
        c = p.calculate(np.asarray(r["endpoint_east_north_km"]))
        r.update(
            coefficient=c["coefficient"],
            unused_phase_coordinates=unused_count(p, entries),
            corrected_selection_loss=r["negative_twice_elbo"]
            - unused_count(p, entries) * unused_student_gap(d["model"]["nu"]),
        )
    return dict(
        arms=pair,
        paired_valid=bool(
            valid(pair, half_width_km=d['scan'].search_region.half_width_km)
            and all(r["final_phase_change_s"] <= 0.01 for r in pair.values())
        ),
        node=node,
        entries=entries,
        means=means,
        constrained_refinement_attempted=attempted,
    )


def trial(d, offers):
    result = fit_configuration(d, *configuration(d, offers))
    result["replacements"] = [
        dict(
            original_index=f["original_index"],
            original_norad=f["original_norad"],
            candidate_index=o["candidate_index"],
            norad=o["norad"],
            predictive_gain=f["original"]["score"] - o["score"],
        )
        for f, o in offers
    ]
    return result


def nominate_families(d):
    case = d["case"]
    try:
        p = d["base"]
        rows = []
        families = sorted(
            {
                r["candidate_index"]
                for r, sl in zip(p.rows, p.slices, strict=True)
                if d["keep"][sl].any()
            }
        )
        for target in families:
            data = family_data(d, target)
            data["target"] = target
            if len(data["values"]) < 4:
                continue
            f, e = phase_frequency_grid(
                d["scan"].sky,
                data["times"],
                *d["scan"].search_region.latlon(d["x"]),
                phase_seconds=d["all_means"],
            )
            plus, _ = phase_frequency_grid(
                d["scan"].sky,
                data["times"],
                *d["scan"].search_region.latlon(d["x"]),
                phase_seconds=d["all_means"] + 0.01,
            )
            minus, _ = phase_frequency_grid(
                d["scan"].sky,
                data["times"],
                *d["scan"].search_region.latlon(d["x"]),
                phase_seconds=d["all_means"] - 0.01,
            )
            coarse = coarse_phase_scores(
                data["values"],
                data["radio"] @ data["coefficient"][: data["radio_width"]],
                f * data["q"],
                (plus - minus) / 0.02 * data["q"],
                d["widths"],
                data["base_covariance"],
                data["groups"],
            )
            scores = np.where(e.min(axis=1) >= 0, coarse["score"], np.inf)
            ordered = [
                int(j) for j in np.argsort(scores) if np.isfinite(scores[j]) and j != target
            ][:7]
            pool = [target] + ordered
            candidates = []
            for j in pool:
                candidates.append(candidate_prediction(d, data, j, coarse["aliases"][j]))
            eligible = sorted([r for r in candidates if r["qualified"]], key=lambda r: r["score"])
            original = next(r for r in candidates if r["candidate_index"] == target)
            best = next((r for r in eligible if r["candidate_index"] != target), None)
            gain = original["score"] - best["score"] if best is not None else None
            rows.append(
                dict(
                    original_index=target,
                    original_norad=int(d["scan"].norads[target]),
                    members=data["members"],
                    held_observation_ids=data["held_ids"],
                    held_points=len(data["values"]),
                    coarse_candidate_count=len(scores),
                    candidates=candidates,
                    original=original,
                    best=best,
                    predictive_gain=gain,
                    search_penalty=float(2 * np.log(len(scores))),
                    all_held_points_disjoint_from_calibration=True,
                    cavity_phase_change_s=data["cavity_phase_change_s"],
                    no_predictive_noise_gate_used_to_veto_a_joint_proposal=True,
                )
            )
        result = dict(
            case=case,
            status="complete",
            families=rows,
            reference_position_used=False,
            no_RF_GPS_future_TLE_or_point_deletion=True,
            incumbent_arms=d["signed"]["policy_arms"],
        )
    except Exception as exc:
        result = dict(case=case, status="failed", error=repr(exc))
    return result


def fit_cavity_proposals(d, nom):
    case = d["case"]
    try:
        baseline = d["signed"]["policy_arms"]
        replay = {}
        base_corrected = {}
        reference_repairs = {}
        for arm, r in baseline.items():
            p = make_event_problem(
                d["scan"],
                d["node"],
                d["keep"],
                arm,
                np.asarray(r["phase_reference"]),
                d["powers"],
                d["means"],
                d["model"],
                [],
            )
            attach_event_predictive(p, d["entries"], d["powers"])
            c = p.calculate(np.asarray(r["endpoint_east_north_km"]))
            delta = c["negative_twice_elbo"] - r["negative_twice_elbo"]
            if abs(delta) >= 1e-05:
                np.testing.assert_allclose(
                    r["phase_reference"],
                    np.asarray(r["state"]["phases"])[p.labels],
                    rtol=0,
                    atol=1e-12,
                )

                def posterior(reference, parameters, arm=arm):
                    probe = make_event_problem(
                        d["scan"],
                        d["node"],
                        d["keep"],
                        arm,
                        reference,
                        d["powers"],
                        d["means"],
                        d["model"],
                        [],
                    )
                    return probe.state(parameters)["phases"][probe.labels]

                reference = legacy_phase_reference(
                    r["history"], np.zeros(len(d["means"])), posterior
                )
                p = make_event_problem(
                    d["scan"],
                    d["node"],
                    d["keep"],
                    arm,
                    reference,
                    d["powers"],
                    d["means"],
                    d["model"],
                    [],
                )
                attach_event_predictive(p, d["entries"], d["powers"])
                c = p.calculate(np.asarray(r["endpoint_east_north_km"]))
                reference_repairs[arm] = dict(
                    archived_reference=np.asarray(r["phase_reference"]),
                    replayed_fit_reference=reference,
                    original_loss_difference=delta,
                    loss_difference_after_replay=c["negative_twice_elbo"]
                    - r["negative_twice_elbo"],
                    reconstructed_from_saved_phase_round_endpoints_without_position_refitting=True,
                )
                delta = c["negative_twice_elbo"] - r["negative_twice_elbo"]
            assert abs(delta) < 1e-05
            replay[arm] = delta
            base_corrected[arm] = r["negative_twice_elbo"] - unused_count(
                p, d["entries"]
            ) * unused_student_gap(d["model"]["nu"])
        families = sorted(
            [f for f in nom["families"] if f["best"] is not None and f["predictive_gain"] > 0],
            key=lambda f: f["predictive_gain"],
            reverse=True,
        )[:4]
        offers = [(f, f["best"]) for f in families]
        hypotheses = [[o] for o in offers]
        if len(offers) >= 2:
            hypotheses.append(offers[:2])
        hypotheses = [
            h
            for h in hypotheses
            if not {f["original_index"] for f, o in h} & {o["candidate_index"] for f, o in h}
        ]
        trials = []
        for hypothesis in hypotheses:
            record = trial(d, hypothesis)
            trials.append(record)
        candidates = [r for r in trials if r["paired_valid"]]
        best = (
            min(candidates, key=lambda r: r["arms"]["c0"]["corrected_selection_loss"])
            if candidates
            else None
        )
        penalty = float(2 * np.log(max(1, len(d["scan"].norads) * len(nom["families"]))))
        gain = (
            base_corrected["c0"] - best["arms"]["c0"]["corrected_selection_loss"] if best else None
        )
        accepted = bool(best is not None and gain > penalty)
        result = dict(
            case=case,
            status="complete",
            accepted=accepted,
            trials=trials,
            selected=best if accepted else None,
            baseline_arms=baseline,
            policy_arms=best["arms"] if accepted else baseline,
            baseline_corrected_loss=base_corrected,
            search_penalty=penalty,
            selection_gain=gain,
            original_mask=d["keep"],
            powers=d["powers"],
            model=d["model"],
            baseline_node=d["node"],
            baseline_entries=d["entries"],
            baseline_means=d["means"],
            same_full_original_observations_and_physical_priors_in_all_trials=True,
            original_aliases_changed_only_in_explicit_complete_family_hypotheses=True,
            original_both_arm_residual_gates_required=True,
            unused_student_prior_gap_removed_only_if_no_curved_or_predictive_data=True,
            null_objective_replay_differences=replay,
            no_GPS_RF_future_TLE_or_point_deletion=True,
            legacy_fit_reference_replay=reference_repairs,
        )
    except Exception as exc:
        result = dict(case=case, status="failed", accepted=False, error=repr(exc))
    return result
