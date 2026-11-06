"""Matched predictive-only position trials, exact replay and scoped adoption.

Inputs are owned numerical contexts and annotation records. File publication,
worker orchestration and time-budget admission are outside this module.
"""

import numpy as np
from scipy.optimize import minimize

from leo.analysis.localization_v3 import numerical_policy as numerics
from leo.analysis.localization_v3.conditional_satellite import (
    attach_conditional_satellite_refresh,
    exact_shared_replay,
)
from leo.analysis.localization_v3.event_position import (
    attach_event_predictive,
    cached,
    make_event_problem,
    summary,
)
from leo.analysis.localization_v3.gap_fragments import gap_context, source_digest
from leo.analysis.localization_v3.history_policy import pair_passes
from leo.analysis.localization_v3.new_family import NewFamily, resolution_audit
from leo.analysis.localization_v3.position import fit
from leo.analysis.localization_v3.prediction import check_predictive_role
from leo.analysis.localization_v3.recovery_acceptance import (
    numerical_only,
    owner_changes,
    shared_family_route,
    single_candidate,
)
from leo.analysis.localization_v3.recovery_fragments import (
    inactive_fragment_context,
    original_graph_view,
)
from leo.analysis.localization_v3.recovery_gates import exact_gate_replay, gate_slacks
from leo.analysis.localization_v3.recovery_inventory import memberships
from leo.analysis.localization_v3.recovery_partitions import require_distinct_annotation
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.analysis.research.position_calculation_cache import copying_position_cache
from leo.analysis.research.retained_track_likelihood import profile

ARMS = ("c0", "fitted_c")


def attach_recovery_predictive(p, entries, powers):
    """Later recovery's copy-preserving cache; leave earlier policy variant intact."""
    if entries:
        p.calculate = copying_position_cache(p.calculate)
    return attach_event_predictive(p, entries, powers)


def _problem(d, arm, reference, entries, *, conditional_families=None):
    kwargs = {"base_problem_factory": d["problem_factory"]} if "problem_factory" in d else {}
    p = make_event_problem(
        d["scan"],
        d["node"],
        d["keep"],
        arm,
        np.asarray(reference),
        d["powers"],
        d["means"],
        d["model"],
        [],
        **kwargs,
    )
    numerics.check_problem(d, p)
    attach_recovery_predictive(p, entries, d["powers"])
    if conditional_families is not None:
        attach_conditional_satellite_refresh(p, entries, d["powers"], conditional_families)
    return cached(p)


def _targets(context, inventory, annotations, *, shared):
    d = context
    p0, _ = d["problems"]["c0"]
    count = len(d["scan"].tracks)
    targets, receipts, fragments = [], [], []
    used = {o for e in d["entries"] for o in e["observation_ids"]}
    used.update(
        o
        for i, sl in zip(p0.members, p0.slices, strict=True)
        for o, k in zip(d["scan"].tracks[i]["observation_ids"], d["keep"][sl], strict=True)
        if k
    )
    for validation in annotations:
        result, protocol = validation["result"], validation["protocol"]
        vote = identity_consensus(result["folds"], score_name="conditional_target")
        if vote["status"] != "conditionally_supported_identity":
            raise ValueError("identity not supported under supplied validation")
        if result.get("graph_bundle") or protocol.get("measurement_refinement"):
            raise ValueError("This stage requires original graph or inactive-fragment evidence")
        if "gap_source" in validation:
            source = validation["gap_source"]
            if source_digest(source) != protocol["target"]["gap_source_sha256"]:
                raise ValueError("gap source changed since annotation")
            d, target = gap_context(
                d, inventory, source, result["track_id"], d["native_observations"]
            )
            for key in ("track_id", "track_index", "component", "observation_ids"):
                if target[key] != protocol["target"][key]:
                    raise ValueError("gap target changed since annotation")
        elif result.get("inactive_graph_fragment"):
            d, target = inactive_fragment_context(d, inventory, result["track_id"])
            for key in ("track_id", "component", "parent_track_index", "observation_ids"):
                if target[key] != protocol["target"][key]:
                    raise ValueError(
                        "inactive fragment observations or parent changed since annotation"
                    )
            fragments.append(result["track_id"])
        else:
            target = next(t for t in inventory["tracks"] if t["track_id"] == result["track_id"])
        i = target["track_index"]
        track = d["scan"].tracks[i]
        j = int(np.flatnonzero(d["scan"].norads == vote["norad"])[0])
        active = any(
            r["candidate_index"] == j and d["keep"][sl].any()
            for r, sl in zip(p0.rows, p0.slices, strict=True)
        )
        if shared:
            check_predictive_role(p0, i, True)
            if j not in p0.labels or not active:
                raise ValueError("shared inclusion requires an active calibrated family")
        else:
            if j in p0.labels and active:
                raise ValueError("target family has active calibration observations")
            if any(e["candidate_index"] == j for e in d["entries"]):
                raise ValueError("target family already has predictive observations")
        aliases = {
            q["alias"]
            for f in result["folds"]
            for q in f["proposals"]
            if q["norad"] == vote["norad"]
        }
        if len(aliases) != 1:
            raise ValueError("alias not stable across randomized partitions")
        if used.intersection(track["observation_ids"]):
            raise ValueError("target duplicates retained observations")
        used.update(track["observation_ids"])
        targets.append(
            dict(
                track_index=i,
                component=track["key"],
                candidate_index=j,
                norad=vote["norad"],
                alias=next(iter(aliases)),
                points=len(track["times"]),
                observation_ids=track["observation_ids"],
            )
        )
        receipts.append(dict(annotation=vote))
    return d, targets, receipts, fragments, count


def fit_shared(context, inventory, annotations, *, conditional_satellite_refresh=False,
               map_arms=None, control_cache=None):
    d, targets, receipts, fragments, count = _targets(context, inventory, annotations, shared=True)
    protocol = dict(
        targets=targets,
        annotation_receipts=receipts,
        matched_c_arms=True,
        phase_rounds=5,
        steps=48,
        start=[0, 0],
        position_fit="regional_unconstrained",
        box_width_km=25,
        target_calibrates_receiver=False,
        target_updates_unobserved_satellite_parameters=False,
        original_noise_weights_and_priors=True,
        original_noise_weights=True,
        noise_policy="original",
        orphan_phase_refresh=False,
        orphan_orbit_prior=False,
        GPS_used=False,
        future_TLE=False,
        target_orbit_prior=False,
        shared_satellite_refresh=False,
        conditional_satellite_refresh=conditional_satellite_refresh,
        inactive_graph_member_as_predictive=True,
        inactive_fragment_sources=fragments,
        graph_bundle_sources=[],
        excluded_predictive_parameter_uncertainty_conditioned_away=conditional_satellite_refresh,
        native_branches=None,
        native_sources=[],
        original_graph_count=count,
    )
    native = any("gap_source" in a for a in annotations)
    if native:
        protocol["inactive_graph_member_as_predictive"] = False
        protocol["native_sources"] = [
            a["protocol"]["target"]["gap_source_sha256"] for a in annotations
        ]
    result = dict(protocol=protocol)
    variants = [("control", [])] + [(f"target_{k}", [t]) for k, t in enumerate(targets)]
    if len(targets) > 1:
        variants.append(("combined", targets))
    for name, extras in variants:
        entries = d["entries"] + extras
        fit_context = (control_cache.context(d, 'fit_shared', conditional_satellite_refresh)
                       if control_cache is not None and name == 'control' else d)

        def fit_arm(arm, entries=entries, extras=extras, d=fit_context):
            x, reference, history = np.zeros(2), np.zeros(len(d["means"])), []
            for _ in range(5):
                p = _problem(
                    d,
                    arm,
                    reference,
                    entries,
                    conditional_families=(
                        [t["candidate_index"] for t in targets]
                        if conditional_satellite_refresh
                        else None
                    ),
                )
                fitted = fit(p, x, iterations=48)
                x = np.asarray(fitted["parameters"])
                reference, check = numerics.refresh(d, p, p.state(x)["phases"][p.labels], reference)
                history.append(dict(endpoint_east_north_km=x, fit=fitted, **check))
            row = summary(p, x, entries)
            _, _, ids, owners = memberships(original_graph_view(p, count), x, entries)
            old = set(inventory["policy"][arm]["proposed_associated_ids"])
            receiver_change = p.calculate(x).get(
                "shared_satellite_receiver_change", row["linear_calibration_max_difference"]
            )
            if receiver_change > 1e-10:
                raise ValueError("predictive data changed receiver calibration at fixed position")
            row.update(
                history=history,
                final_phase_change_s=check["phase_change_s"],
                proposed_associated_ids=sorted(ids),
                proposed_owners=owners,
                added_points=len(ids - old),
                lost_points=len(old - ids),
                targets=[
                    g
                    for g in row["linear_gates"]
                    if g["component"] in {e["component"] for e in extras}
                ],
            )
            if extras:
                calc, diagnostics = p.calculate(x), []
                for entry, sl in zip(p.linear_entries, p.linear_slices, strict=True):
                    if entry not in extras:
                        continue
                    t = p.scan.tracks[entry["track_index"]]
                    raw = calc["linear_raw_prediction_residual_hz"][sl]
                    terms = profile(
                        raw,
                        np.zeros(len(raw)),
                        *p.scan.white[entry["track_index"]],
                        bias_sigma=300.0,
                    )
                    diagnostics.append(
                        dict(
                            component=entry["component"],
                            norad=entry["norad"],
                            times_s=t["times"],
                            CFO_hz=t["values"],
                            predicted_CFO_hz=t["values"] - raw,
                            residual_hz=terms["residual"][0],
                            RMS_hz=float(terms["rms"][0]),
                            bias_hz=float(terms["bias"][0]),
                        )
                    )
                row["target_diagnostics"] = diagnostics
                if native:
                    row["native_target_diagnostics"] = diagnostics
            if conditional_satellite_refresh:
                row["shared_satellite_replay"] = exact_shared_replay(p, x, entries)
            return row

        def compute_pair():
            return dict(zip(ARMS, numerics.map_calibration_arms(d, fit_arm, ARMS, map_arms),
                            strict=True))

        pair = (compute_pair() if control_cache is None else control_cache.pair(
            compute_pair, name == 'control', 'fit_shared', fit_context, inventory, count,
            conditional_satellite_refresh))
        valid = pair_passes(pair, include_linear=True) and all(
            r["lost_points"] == 0 and r["final_phase_change_s"] <= 0.01 for r in pair.values()
        )
        if conditional_satellite_refresh:
            valid = valid and all(
                r["shared_satellite_replay"]["phases_in_bounds"]
                and r["shared_satellite_replay"]["maximum_phase_linearization_error_hz"] <= 1
                for r in pair.values()
            )
        result[name] = dict(
            arms=pair,
            baseline=inventory["policy"],
            paired_valid=valid,
            target_entries=extras,
            original_calibration_mask=d["keep"],
            target_calibrates_receiver=False,
            target_updates_unobserved_satellite_parameters=False,
            orphan_phase_refresh=False,
            orphan_orbit_prior=False,
            noise_policy="original",
            position_fit="regional_unconstrained",
            target_orbit_prior=False,
            shared_satellite_refresh=False,
            conditional_satellite_refresh=conditional_satellite_refresh,
            no_production_change=True,
        )
    return result


def fit_new(context, inventory, annotations, *, optimizer="lbfgsb", map_arms=None,
            control_cache=None):
    if optimizer not in ("lbfgsb", "powell"):
        raise ValueError("unknown matched position optimizer")
    d, targets, _, fragments, count = _targets(context, inventory, annotations, shared=False)
    family = NewFamily(
        d["scan"], targets, d["model"], phase_step=0.025, allow_uncalibrated_label=True
    )
    protocol = dict(
        targets=targets,
        validation=[a["result"]["track_id"] for a in annotations],
        family_prior=family.receipt,
        inactive_fragment_sources=fragments,
        measurement_refinements=[],
        graph_bundle_sources=[],
        original_graph_count=count,
        optimizer=optimizer + " normalized joint objective",
        maxiter=48,
        maxfun=240,
        phase_rounds=5,
        start=[0, 0],
        box_width_km=25,
        control_uses_same_optimizer=True,
        c0_vs_fitted_c=True,
        GPS_used=False,
        future_TLE=False,
        phase_step_s=0.025,
        uncalibrated_label=True,
        phase_resolution_audit=True,
        postfit_audit_evaluations_per_arm=15,
    )
    result = dict(protocol=protocol)
    for variant, include in [("control", False), ("new_family", True)]:
        fit_context = (control_cache.context(d, 'fit_new', optimizer)
                       if control_cache is not None and variant == 'control' else d)

        def fit_arm(arm, include=include, d=fit_context):
            x, reference, history = np.zeros(2), np.zeros(len(d["means"])), []
            for _ in range(5):
                p = _problem(d, arm, reference, d["entries"])

                def objective(z, p=p, include=include):
                    c = p.calculate(z)
                    penalty = float(np.sum(np.minimum(0, c["elevation"][p.keep]) ** 2) / 4)
                    return (
                        c["negative_twice_elbo"]
                        + penalty
                        + (family.evaluate(p, z, d["powers"], d["entries"]) if include else 0.0)
                    )

                if optimizer == "lbfgsb":
                    opt = numerics.minimize(
                        d,
                        minimize,
                        objective,
                        x,
                        method="L-BFGS-B",
                        bounds=[(-12.5, 12.5)] * 2,
                        options=dict(
                            maxiter=48, maxfun=240, eps=0.001, ftol=1e-10, gtol=1e-4, maxls=20
                        ),
                    )
                else:
                    opt = numerics.minimize(
                        d,
                        minimize,
                        objective,
                        x,
                        method="Powell",
                        bounds=[(-12.5, 12.5)] * 2,
                        options=dict(maxiter=48, maxfev=240, ftol=1e-10, xtol=1e-5),
                    )
                x = np.asarray(opt.x)
                reference, check = numerics.refresh(d, p, p.state(x)["phases"][p.labels], reference)
                history.append(
                    dict(
                        endpoint_east_north_km=x,
                        objective=float(opt.fun),
                        success=bool(opt.success),
                        message=str(opt.message),
                        nfev=opt.nfev,
                        **check,
                    )
                )
            row = summary(p, x, d["entries"])
            _, _, ids, _ = memberships(original_graph_view(p, count), x, d["entries"])
            old = set(inventory["policy"][arm]["proposed_associated_ids"])
            if include:
                detail = family.evaluate(p, x, d["powers"], d["entries"], details=True)
                row["family"] = detail
                row["incumbent_objective"] = row["negative_twice_elbo"]
                row["negative_twice_elbo"] += detail["negative_twice_log_density"]
                row["linear_gates"] += detail["gates"]
                ids.update(o for e in targets for o in e["observation_ids"])
                row["phase_resolution_audit"] = resolution_audit(
                    family, p, x, d["powers"], d["entries"], d["model"]
                )
            row.update(
                history=history,
                final_phase_change_s=check["phase_change_s"],
                proposed_associated_ids=sorted(ids),
                added_points=len(ids - old),
                lost_points=len(old - ids),
            )
            return row

        def compute_pair():
            return dict(zip(ARMS, numerics.map_calibration_arms(d, fit_arm, ARMS, map_arms),
                            strict=True))

        pair = (compute_pair() if control_cache is None else control_cache.pair(
            compute_pair, variant == 'control', 'fit_new', fit_context, inventory, count,
            optimizer))
        valid = pair_passes(pair, include_linear=True) and all(
            v["lost_points"] == 0
            and v["history"][-1]["success"]
            and v["final_phase_change_s"] <= 0.01
            for v in pair.values()
        )
        if include:
            valid = valid and all(
                v["family"]["phase_boundary_mass"] < 0.01
                and v["phase_resolution_audit"]["local_agreement"]
                for v in pair.values()
            )
        result[variant] = dict(
            arms=pair,
            baseline=inventory["policy"],
            paired_valid=valid,
            target_entries=targets if include else [],
            no_production_change=True,
            receiver_calibration_from_target=False,
            shared_predictive_uncertainty=True,
            phase_resolution_checked=bool(include),
        )
    return result


def audit_inclusion(context, inventory, annotations, trial, *, shared):
    d, targets, _, _, count = _targets(context, inventory, annotations, shared=shared)
    family = (
        None
        if shared
        else NewFamily(
            d["scan"], targets, d["model"], phase_step=0.025, allow_uncalibrated_label=True
        )
    )
    incumbent, controls, rows = {}, {}, []
    for arm, (p, x) in d["problems"].items():
        _, _, ids, incumbent[arm] = memberships(p, x, d["entries"])
        if ids != set(inventory["policy"][arm]["proposed_associated_ids"]):
            raise ValueError("incumbent membership replay failed")
    for role in ("control", "target_0" if shared else "new_family"):
        saved = trial[role]
        entries = d["entries"] + (saved["target_entries"] if shared else [])
        for arm, v in saved["arms"].items():
            p = _problem(
                d,
                arm,
                v["phase_reference"],
                entries,
                conditional_families=(
                    [t["candidate_index"] for t in targets]
                    if shared and trial["protocol"].get("conditional_satellite_refresh")
                    else None
                ),
            )
            x = np.array(v["endpoint_east_north_km"])
            objective = p.calculate(x)["negative_twice_elbo"]
            _, _, ids, owners = memberships(original_graph_view(p, count), x, entries)
            target = refined = None
            if not shared and role == "new_family":
                target = family.evaluate(p, x, d["powers"], d["entries"], details=True)
                refined = family.evaluate(
                    p, x, d["powers"], d["entries"], details=True, refine_phase=True
                )
                if (
                    abs(
                        target["negative_twice_log_density"]
                        - v["family"]["negative_twice_log_density"]
                    )
                    > 1e-6
                ):
                    raise ValueError("family density failed replay")
                objective += target["negative_twice_log_density"]
                for entry in targets:
                    if ids.intersection(entry["observation_ids"]):
                        raise ValueError("target duplicates incumbent evidence")
                    ids.update(entry["observation_ids"])
                    owners.update({o: entry["norad"] for o in entry["observation_ids"]})
            difference = objective - v["negative_twice_elbo"]
            if abs(difference) > 1e-5 or ids != set(v["proposed_associated_ids"]):
                raise ValueError("objective or membership failed replay")
            if shared and owners != v["proposed_owners"]:
                raise ValueError("owners failed replay")
            if role == "control":
                controls[arm] = owners
            labels = {
                r["candidate_index"]
                for r, sl in zip(p.rows, p.slices, strict=True)
                if p.keep[sl].any()
            }
            labels.update(e["candidate_index"] for e in entries)
            exact = []
            # Each replay changes only one family's orbit. Evaluate unchanged
            # gates once at this fixed arm/role/position, retaining every key.
            base_slacks = gate_slacks(p, x, entries) if labels else None
            for j in sorted(labels):
                p.explicit_phase_family = j
                exact.append(dict(
                    norad=int(p.scan.norads[j]),
                    **exact_gate_replay(p, x, entries, base_slacks=base_slacks),
                ))
            _, check = numerics.refresh(d, p, p.state(x)["phases"][p.labels], p.reference)
            old_changes = owner_changes(incumbent[arm], owners)
            control_changes = owner_changes(controls[arm], owners)
            if shared:
                receiver_change = p.calculate(x).get(
                    "shared_satellite_receiver_change", v["linear_calibration_max_difference"]
                )
                verified = (
                    not old_changes
                    and not control_changes
                    and all(q["all_pass"] for q in exact)
                    and check["phase_change_s"] <= 0.01
                    and receiver_change <= 1e-10
                )
                row = dict(
                    role=role,
                    arm=arm,
                    objective_difference=difference,
                    phase_reference_check=check,
                    exact_family_replays=exact,
                    incumbent_ownership_changes=old_changes,
                    control_ownership_changes=control_changes,
                    receiver_coefficient_change=receiver_change,
                    verified=verified,
                )
            else:
                row = dict(
                    role=role,
                    arm=arm,
                    objective_difference=float(difference),
                    incumbent_ownership_changes=old_changes,
                    control_ownership_changes=control_changes,
                    phase_reference_check=check,
                    exact_incumbent_family_replays=exact,
                    target=target,
                    continuous_target=refined,
                    owners=owners,
                )
                row["verified"] = (
                    check["phase_change_s"] <= 0.01
                    and all(r["all_pass"] for r in exact)
                    and not old_changes
                    and not control_changes
                    and (
                        target is None
                        or (
                            all(g["compatible"] for g in target["gates"])
                            and all(g["compatible"] for g in refined["gates"])
                            and target["receiver_calibration_change"] == 0
                        )
                    )
                )
            rows.append(row)
    result = dict(
        rows=rows,
        all_verified=all(r["verified"] for r in rows),
        no_refit=True,
        no_acceptance_changes=True,
    )
    result[
        "exact_orbits_replaced_one_family_at_a_time"
        if shared
        else "incumbent_orbits_replaced_one_family_at_a_time"
    ] = True
    return result


def include_annotation(context, inventory, annotation):
    vote = identity_consensus(annotation["result"]["folds"], score_name="conditional_target")
    if vote["status"] != "conditionally_supported_identity":
        return dict(status=vote["status"], annotation=vote, selected=None)
    require_distinct_annotation(annotation["result"], annotation["protocol"])
    shared = shared_family_route(annotation["result"]["folds"], vote["norad"])
    trial = (fit_shared if shared else fit_new)(context, inventory, [annotation])
    audit = audit_inclusion(context, inventory, [annotation], trial, shared=shared)
    selected = single_candidate(inventory, trial, audit, shared)
    result = dict(annotation=vote, shared_family=shared, trial=trial, audit=audit, retry=None)
    if (
        not shared
        and selected is None
        and numerical_only(trial["control"], trial["new_family"], audit)
    ):
        retry = fit_new(context, inventory, [annotation], optimizer="powell")
        replay = audit_inclusion(context, inventory, [annotation], retry, shared=False)
        result["retry"] = dict(trial=retry, audit=replay)
        selected = single_candidate(inventory, retry, replay, False)
    result.update(
        status="qualified_candidate" if selected else "inclusion_rejected", selected=selected
    )
    return result
