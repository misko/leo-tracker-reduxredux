"""Replay frozen predictive competitions with a larger numerical reference.

No new nomination, catalogue, folds, aliases, target phase support or calibration
role is introduced. Inputs are owned contexts and explicitly supplied evidence.
"""

import copy
import hashlib

import numpy as np

from leo.analysis.localization_v3.phase_reference import reference_domain
from leo.analysis.localization_v3.prediction import (
    check_predictive_role,
    fit_training,
    prediction_models,
)
from leo.analysis.localization_v3.recovery_fragments import inactive_fragment_context
from leo.analysis.localization_v3.recovery_partitions import require_distinct_annotation
from leo.analysis.research.grouped_prediction import identity_consensus, replay_split
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD

ARMS = ("c0", "fitted_c")


def target_context(context, inventory, frozen, protocol):
    if (
        frozen.get("graph_bundle")
        or protocol["target"].get("native_branch_source")
        or protocol.get("measurement_refinement")
    ):
        raise ValueError("numerical replay requires original graph or inactive-fragment evidence")
    if frozen.get("inactive_graph_fragment"):
        changed, target = inactive_fragment_context(context, inventory, frozen["track_id"])
    else:
        changed = context
        target = next(t for t in inventory["tracks"] if t["track_id"] == frozen["track_id"])
    expected = protocol["target"]
    track = changed["scan"].tracks[target["track_index"]]
    for key in ("track_id", "track_index", "component", "observation_ids"):
        if key in expected and target.get(key) != expected[key]:
            raise ValueError(f"frozen target {key} changed")
    appended = bool(frozen.get("inactive_graph_fragment"))
    expected_ids = (
        expected["observation_ids"]
        if appended
        else expected.get("all_track_observation_ids", expected["observation_ids"])
    )
    if track["key"] != frozen["component"] or set(track["observation_ids"]) != set(expected_ids):
        raise ValueError("frozen annotation observations or component changed")
    if (
        not appended
        and "all_track_observation_ids" in expected
        and list(track["observation_ids"]) != list(expected_ids)
    ):
        raise ValueError("frozen chronological graph observations changed")
    focus = (protocol.get("partition_plan") or {}).get("target_times_s")
    if focus is not None and not np.array_equal(np.asarray(track["times"]), np.asarray(focus)):
        raise ValueError("frozen annotation target timestamps changed")
    return changed, target


def replay_annotation(context, inventory, annotation):
    """Re-evaluate every saved proposal; never renominate using a changed fit."""
    frozen, protocol = annotation["result"], annotation["protocol"]
    require_distinct_annotation(frozen, protocol)
    if not has_phase_overflow(frozen):
        raise ValueError("reference30 replay requires saved phase overflow metadata")
    if protocol.get("phase_rounds", 5) != 5 or protocol.get("position_steps", 48) != 48:
        raise ValueError("frozen training budget differs from unchanged five-by-48 implementation")
    if protocol.get("fixed_noise_hz", 150) != 150 or protocol.get("phase_box_s", [-15, 15]) != [
        -15,
        15,
    ]:
        raise ValueError("frozen physical noise or target phase policy differs")
    original_competition = competition_signature(frozen)
    base, _ = context["problems"]["c0"]
    d, target = target_context(context, inventory, frozen, protocol)
    i = target["track_index"]
    track = d["scan"].tracks[i]
    check_predictive_role(base, i, protocol.get("inactive_curved_member_as_predictive", False))
    n = len(base.flat_times)
    full_times = np.r_[base.flat_times, track["times"]]
    receipt = dict(
        reference_limit_s=30.0,
        baseline15_receipts_reused=True,
        frozen_competition=True,
        observations_candidates_aliases_splits_priors_starts_and_budgets_unchanged=True,
        physical_phase_prior_and_target_support_unchanged=True,
        GPS_used=False,
        new_RF=False,
        new_TLE=False,
    )
    updated_protocol = copy.deepcopy(protocol)
    updated_protocol.update(
        reference_limit_s=30.0, frozen_competition=True, numerical_replay=receipt
    )
    folds = []
    for fold in frozen["folds"]:
        train, held = replay_split(full_times, fold["split"])
        keep, tt, th = d["keep"] & train[:n], train[n:], held[n:]
        if tt.sum() < 8 or th.sum() < 4:
            raise ValueError("frozen target grouping lacks original minimum support")
        updated = copy.deepcopy(fold)
        fits = {}
        masks = dict(
            graph_training=fingerprint(keep),
            target_training=fingerprint(tt),
            target_held=fingerprint(th),
        )
        for arm in ARMS:
            p, x, meta = fit_training(
                d, d["node"], keep, arm, reference_limit_s=30.0, record_optimizer=True
            )
            np.testing.assert_array_equal(p.keep, keep)
            meta["final_training_reference_domain"] = check_bank(p, x)
            fits[arm] = p, x, meta
        for proposal in updated["proposals"]:
            j = proposal["candidate_index"]
            if int(d["scan"].norads[j]) != proposal["norad"]:
                raise ValueError("frozen candidate catalogue identity changed")
            for arm, (p, x, meta) in fits.items():
                mu, cov, lp, phases, elev, prior = prediction_models(
                    d,
                    p,
                    x,
                    i,
                    j,
                    phase_step=protocol["phase_step_s"],
                    uncalibrated_phase_mixture=protocol["uncalibrated_phase_mixture"],
                )
                domains = []
                for boundary in (float(phases.min()), float(phases.max())):
                    domain = reference_domain(
                        p.sky["time_s"],
                        track["times"],
                        np.zeros(len(track["times"]), int),
                        np.array([boundary]),
                    )
                    if not domain["in_domain"]:
                        raise ValueError("target prediction leaves frozen causal orbit bank")
                    domains.append(domain)
                observed = track["values"] + proposal["alias"] * PERIOD
                if np.isfinite(lp).any():
                    score = mixture_prediction(observed, mu, cov, lp, tt, th)
                    weights = score["training_mixture_weights"]
                    visible = float(elev[weights > 1e-6].min())
                    mean = float(weights @ phases)
                    sd = float(np.sqrt(weights @ ((phases - mean) ** 2)))
                    boundary_mass = (
                        float(weights[abs(phases) >= 14.9].sum())
                        if len(phases) > 1
                        else float(abs(phases[0]) >= 14.9)
                    )
                else:
                    score = dict(negative_twice_log_density=1e30, rms_hz=1e15, unobservable=True)
                    visible = float(elev.max())
                    mean = sd = boundary_mass = None
                old = proposal["arms"][arm]
                value = copy.deepcopy(old)
                value.update(
                    copy.deepcopy(meta),
                    scores=dict(conditional_target=score, target=score),
                    prior=prior,
                    minimum_target_elevation_deg=visible,
                    target_phase_training_mean_s=mean,
                    target_phase_training_sigma_s=sd,
                    target_phase_boundary_mass=boundary_mass,
                    target_enters_calibration_equations=False,
                    mask_sha256=masks,
                    target_reference_domain=domains,
                    baseline15_score_difference=score["negative_twice_log_density"]
                    - old["scores"]["conditional_target"]["negative_twice_log_density"],
                )
                proposal["arms"][arm] = value
        folds.append(updated)
    result = copy.deepcopy(frozen)
    result.update(
        folds=folds,
        annotation=identity_consensus(folds, score_name="conditional_target"),
        reference_limit_s=30.0,
        numerical_replay=receipt,
        no_production_change=True,
    )
    if competition_signature(result) != original_competition:
        raise ValueError("frozen competition changed during replay")
    require_distinct_annotation(result, updated_protocol)
    return dict(protocol=updated_protocol, result=result)


def has_phase_overflow(value):
    """Any saved round may clip even when the final round no longer clips."""
    if isinstance(value, dict):
        if value.get("phase_outside_reference_window") is True:
            return True
        overflow = value.get("maximum_phase_overflow_s")
        if isinstance(overflow, (int, float)) and np.isfinite(overflow) and (overflow > 0):
            return True
        return any(has_phase_overflow(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_phase_overflow(v) for v in value)
    return False


def fingerprint(mask):
    return hashlib.sha256(np.asarray(mask, np.uint8).tobytes()).hexdigest()


def competition_signature(result):
    return [
        (
            f["seed"],
            copy.deepcopy(f["split"]),
            [(q["candidate_index"], q["norad"], q["alias"]) for q in f["proposals"]],
        )
        for f in result["folds"]
    ]


def check_bank(p, x):
    phase = np.asarray(p.state(x)["phases"])[p.labels]
    check = reference_domain(p.sky["time_s"], p.flat_times, p.flat_labels, phase)
    if not check["in_domain"]:
        raise ValueError("final training phases leave frozen causal orbit bank")
    return check
