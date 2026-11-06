"""Grouped causal satellite annotation, with no authority to add associations."""

import numpy as np

from leo.analysis.localization_v3.prediction import (
    check_predictive_role,
    corrected,
    fit_training,
    nominate,
    prediction_models,
    restore_training,
    training_record,
)
from leo.analysis.localization_v3.recovery_fragments import inactive_fragment_context
from leo.analysis.localization_v3.recovery_partitions import partition_schedule, planned_split
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.track_recovery_diagnostics import profile_rate

ARMS = ("c0", "fitted_c")


def annotate_fold(
    d, i, full_times, n, seed, plan, *, candidates, phase_step, shifted_origin, on_proposal=None,
    training=None,
):
    """Evaluate one predeclared grouped split without adopting associations."""
    track = d["scan"].tracks[i]
    if not shifted_origin and len(np.unique(np.floor(track["times"] / 12))) < 3:
        return dict(
            attempt=dict(status="insufficient_group_support", seed=seed), nomination=None, fold=None
        )
    train, held, split = planned_split(full_times, track["times"], seed, plan)
    train_target, held_target = train[n:], held[n:]
    if train_target.sum() < 8 or held_target.sum() < 4:
        return dict(
            attempt=dict(status="insufficient_group_support", seed=seed, split=split),
            nomination=None,
            fold=None,
        )
    keep = d["keep"] & train[:n]
    if training is None:
        base = {a: fit_training(d, d["node"], keep, a) for a in ARMS}
    else:
        base = {a: restore_training(d, keep, a, training[a]) for a in ARMS}
    offers, receipt = nominate(d, base, i, train_target, candidates)
    nomination = dict(selected=offers, nomination=receipt, split=split)
    proposals = []
    for offer in offers:
        j = offer["candidate_index"]
        norad = int(d["scan"].norads[j])
        bank = {key: d["scan"].sky[key][[j]] for key in ("position_km", "velocity_km_s")}
        bank["time_s"] = d["scan"].sky["time_s"]
        tt = track["times"][train_target]
        frequency, _ = paired_phase_frequency(
            bank,
            tt,
            np.zeros(len(tt), int),
            np.array([offer["phase_s"]]),
            *d["scan"].search_region.latlon(offer["position"]),
        )
        p, x, _ = base["c0"]
        alias = int(
            profile_rate(corrected(p, x, i)[train_target], track["rf_hz"] / 11.5e9 * frequency, tt)[
                "alias"
            ][0]
        )
        observed = track["values"] + alias * PERIOD
        arms = {}
        for arm, (p, x, meta) in base.items():
            means, cov, lp, phases, elevations, prior = prediction_models(
                d, p, x, i, j, phase_step=phase_step, uncalibrated_phase_mixture=True
            )
            if np.isfinite(lp).any():
                score = mixture_prediction(observed, means, cov, lp, train_target, held_target)
                weights = score["training_mixture_weights"]
                visible = float(elevations[weights > 1e-6].min())
                phase_mean = float(weights @ phases)
                phase_sd = float(np.sqrt(weights @ ((phases - phase_mean) ** 2)))
                boundary = (
                    float(weights[abs(phases) >= 14.9].sum())
                    if len(phases) > 1
                    else float(abs(phases[0]) >= 14.9)
                )
            else:
                score = dict(negative_twice_log_density=1e30, rms_hz=1e15, unobservable=True)
                visible = float(elevations.max())
                phase_mean = phase_sd = boundary = None
            arms[arm] = dict(
                **meta,
                scores=dict(conditional_target=score, target=score),
                prior=prior,
                minimum_target_elevation_deg=visible,
                target_phase_training_mean_s=phase_mean,
                target_phase_training_sigma_s=phase_sd,
                target_phase_boundary_mass=boundary,
                target_enters_calibration_equations=False,
            )
        proposal = dict(candidate_index=j, norad=norad, alias=alias, arms=arms)
        proposals.append(proposal)
        if on_proposal is not None:
            on_proposal(seed, proposal)
    fold = dict(seed=seed, split=split, proposals=proposals)
    return dict(attempt=fold, nomination=nomination, fold=fold)


def _annotation_view(context, inventory, track_id, *, inactive_fragment=False,
                     target_record=None, shifted_origin=True):
    d = context
    p0, _ = d["problems"]["c0"]
    if target_record is not None:
        if inactive_fragment or target_record["track_id"] != track_id:
            raise ValueError("explicit target must belong to this prepared predictive view")
        target = target_record
    elif inactive_fragment:
        d, target = inactive_fragment_context(d, inventory, track_id)
    else:
        target = next(
            r for r in inventory["tracks"] if r["track_id"] == track_id and r["current_large"]
        )
    i = target["track_index"]
    track = d["scan"].tracks[i]
    check_predictive_role(p0, i, True)
    full_times = np.r_[p0.flat_times, track["times"]]
    n = len(p0.flat_times)
    seeds, plan = partition_schedule(full_times, track["times"], shifted_origin=shifted_origin)
    return d, target, full_times, n, seeds, plan


def _annotation_training(d, track, full_times, n, seeds, plan, shifted_origin):
    masks = {}
    for seed in seeds:
        if not shifted_origin and len(np.unique(np.floor(track['times'] / 12))) < 3:
            continue
        train, held, _ = planned_split(full_times, track['times'], seed, plan)
        if train[n:].sum() >= 8 and held[n:].sum() >= 4:
            masks[seed] = d['keep'] & train[:n]
    tasks = [(seed, arm) for seed in masks for arm in ARMS]

    def train_arm(task):
        seed, arm = task
        return training_record(d, masks[seed], arm)

    return tasks, train_arm


def prepare_training_batch(context, inventory, targets, mapper):
    """Prepare independent recipes for explicitly admitted all-work recovery.

    Each target retains its own context, masks and fits. Preparation errors are
    deferred to that target's original stage; worker failures still propagate.
    Stateful numerical replay must keep its existing serial path.
    """
    if context.get('numerical_policy') is not None:
        raise ValueError('Stateful numerical replay cannot batch target training')
    plans, errors = {}, {}
    for index, target in enumerate(targets):
        try:
            d, row, full, n, seeds, plan = _annotation_view(
                context, inventory, target['track_id'],
                inactive_fragment=target['inactive_fragment'])
            plans[index] = _annotation_training(
                d, d['scan'].tracks[row['track_index']], full, n, seeds[:3], plan, True)
        except Exception as error:
            errors[index] = error
    tasks = [(index, seed, arm) for index, (items, _) in plans.items() for seed, arm in items]

    def train(task):
        index, seed, arm = task
        return plans[index][1]((seed, arm))

    records = list(mapper(train, tasks)) if tasks else []
    if len(records) != len(tasks):
        raise ValueError('Incomplete cross-target training recipes')

    def restore(items, values):
        expected = tuple(items)

        def use(operation, requested):
            if tuple(requested) != expected:
                raise ValueError('Prepared annotation training schedule changed')
            return list(values)
        return use

    mappers, offset = {}, 0
    for index, (items, _) in plans.items():
        count = len(items)
        mappers[index] = restore(items, records[offset:offset + count])
        offset += count
    return mappers, errors


def annotate(
    context,
    inventory,
    track_id,
    *,
    inactive_fragment=False,
    candidates=12,
    folds=3,
    phase_step=0.1,
    on_proposal=None,
    target_record=None,
    shifted_origin=True,
    map_folds=None,
    map_training=None,
):
    """Original production nomination and three distinct shifted-block checks.

    The target and withheld calibration points never enter the training equations.
    The returned annotation is conditional on the frozen graph and incumbents;
    later inclusion, paired acceptance and exact ownership checks are still needed.
    """
    d, target, full_times, n, seeds, plan = _annotation_view(
        context, inventory, track_id, inactive_fragment=inactive_fragment,
        target_record=target_record, shifted_origin=shifted_origin)
    p0, _ = context['problems']['c0']
    i = target['track_index']
    track = d['scan'].tracks[i]
    protocol = dict(
        target=target,
        seed_list=seeds[:folds],
        partition_plan=plan,
        block_s=12,
        guard_s=2,
        target_used_for_calibration=False,
        conditional_on_frozen_graph_and_incumbent_identities=True,
        measurement_refinement=None,
        inactive_curved_member_as_predictive=bool(i in p0.members),
        fixed_noise_hz=150,
        unseen_noise_variance_multiplier=2,
        track_bias_sigma_hz=300,
        phase_box_s=[-15, 15],
        phase_step_s=phase_step,
        uncalibrated_phase_mixture=True,
        phase_rounds=5,
        position_steps=48,
        identity_score_name="conditional_target",
        position_uncertainty_integrated=False,
        learned_noise_precision_uncertainty_integrated=False,
        GPS_used=False,
        future_TLE=False,
    )
    results, nominations, attempts = [], {}, {}
    training = {}
    stateful = on_proposal is not None or d.get("numerical_policy") is not None
    if map_training is not None and not stateful:
        tasks, train_arm = _annotation_training(
            d, track, full_times, n, seeds[:folds], plan, shifted_origin)
        records = map_training(train_arm, tasks) if tasks else []
        for (seed, arm), record in zip(tasks, records, strict=True):
            training.setdefault(seed, {})[arm] = record

    def one(seed):
        return annotate_fold(
            d,
            i,
            full_times,
            n,
            seed,
            plan,
            candidates=candidates,
            phase_step=phase_step,
            shifted_origin=shifted_origin,
            on_proposal=on_proposal,
            **({'training': training[seed]} if seed in training else {}),
        )

    # Numerical replay owns mutable ordered receipts. Observational callbacks
    # may also have caller-owned state. Preserve their original serial behavior.
    mapper = (
        map
        if map_folds is None or stateful
        else map_folds
    )
    for seed, row in zip(seeds[:folds], mapper(one, seeds[:folds]), strict=True):
        attempts[seed] = row["attempt"]
        if row["fold"] is not None:
            nominations[seed] = row["nomination"]
            results.append(row["fold"])
    annotation = identity_consensus(results, score_name="conditional_target")
    result = dict(
        component=track["key"],
        track_id=target["track_id"],
        folds=results,
        annotation=annotation,
        graph_bundle=False,
        bundle_member_checks=None,
        inactive_graph_fragment=target.get("inactive_graph_fragment", False),
        identity_score_name="conditional_target",
        inclusion_mode="predictive_only",
        annotation_prototype=True,
        no_accepted_associations=True,
        geometry_only_early_exit=bool(plan and plan.get("geometry_only_early_exit")),
    )
    return dict(protocol=protocol, nominations=nominations, attempts=attempts, result=result)
