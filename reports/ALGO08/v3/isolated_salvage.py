"""Try one independently nominated curve against only the surviving calibration."""

from contextlib import contextmanager
from copy import deepcopy
from math import sqrt
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from fragment_gate_cross import local_gate, sections, state
from provisional_salvage import independent_support


NUMERICAL_ERRORS = (ValueError, AssertionError, FloatingPointError, np.linalg.LinAlgError)


def timings(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def screen_failures(values, points):
    limits = dict(mean_z=3., slope_z=3., maximum_step_z=4., quadratic_bic_gain=10., lag1_acf=4/sqrt(points))
    values = dict(values, lag1_acf=abs(values["lag1_acf"]))
    return {key for key, limit in limits.items() if not np.isfinite(values[key]) or values[key] > limit}


def sole_failure(gate, reason, *, permit_clear_profile):
    cond = gate["conditional_residual_gate"]
    values = [cond["rms_hz"], gate["profile_rms_hz"], gate["profile_bias_hz"], gate["minimum_elevation_deg"]]
    if (not np.isfinite(values).all() or cond["rms_hz"] > 450 or gate["profile_rms_hz"] > 450
            or abs(gate["profile_bias_hz"]) > 3000 or gate["minimum_elevation_deg"] < 0
            or gate["aliases_changed"] or cond["compatible"] or gate["compatible"]):
        return False
    expected = {reason}
    conditional = screen_failures(cond["diagnostics"], gate["points"])
    profiled = screen_failures(gate["profile_diagnostics"], gate["points"])
    return conditional == expected and (profiled == expected or permit_clear_profile and not profiled)


def isolate_node(original, salvaged, admitted):
    """Keep original assignments for every unadmitted salvage proposal."""
    original_rows = original["seed"]["rows"]
    current_rows = salvaged["seed"]["rows"]
    before, after = ([row["component"] for row in records] for records in (original_rows, current_rows))
    if before != after or len(before) != len(set(before)) or not admitted <= set(after):
        raise ValueError("The original and salvaged component order differs")
    keep = deepcopy(original)
    for k, row in enumerate(current_rows):
        if row["component"] in admitted:
            keep["seed"]["rows"][k] = deepcopy(row)
            keep["aliases"][k] = salvaged["aliases"][k]
    return keep


def qualifying(first, current, point, restored, initial, survivors, evidence):
    proposals = independent_support(current, initial, restored, evidence)
    if proposals is None:
        return [], {}
    offers = {row["component"]: row["selected"] for row in evidence if row["selected"] is not None}
    previous, rows = sections(first), sections(current)
    keys = []
    for key in proposals:
        if key not in previous:
            continue
        _, row, _, sl, alias = rows[key]
        _, earlier, _, prior_sl, prior_alias = previous[key]
        offer = offers[key]
        if (earlier["candidate_norad"] == row["candidate_norad"] == offer["norad"]
                and prior_alias == alias == offer["alias"] and prior_sl == sl
                and not initial[sl].any() and not survivors[sl].any()
                and np.isfinite(offer["phase_s"]) and abs(offer["phase_s"]) <= 15):
            keys.append(key)
    evidence = state(current, point, set(keys)) if keys else {}
    passing = []
    for key, fragment in evidence.items():
        ids = fragment["ids"][fragment["mask"]].tolist()
        gate = local_gate(fragment, ids)
        if sole_failure(gate, "slope_z", permit_clear_profile=False):
            passing.append(dict(component=key, ids=ids, gate=gate, original_nomination=offers[key]))
    return passing, dict(signed_contiguous_offers=len(proposals), intact_same_identity_alias=len(keys))


def provisional_gate(trial, point, metrics, target, survivors, audit):
    known = {name: sl for name, (_, _, _, sl, _) in sections(trial).items() if survivors[sl].any()}
    dropped = [row for row in metrics["tracks"] if not row["compatible"]]
    audit["curved_failed_after_fit"] = [row["component"] for row in dropped]
    target_gates = [row for row in metrics["tracks"] if row["component"] == target]
    if len(target_gates) != 1 or not target_gates[0]["compatible"]:
        return "original_target_curved_gate"
    audit["target_after_fit"] = target_gates[0]
    if not dropped:
        return None
    if len(dropped) != 1 or dropped[0]["component"] not in known:
        return "previously_surviving_curved_support_changed"
    name = dropped[0]["component"]
    fragment = state(trial, point, {name})[name]
    gate = local_gate(fragment, dropped[0]["observation_ids"])
    if not sole_failure(gate, "maximum_step_z", permit_clear_profile=True):
        return "previously_surviving_curved_support_changed"
    audit["pending_paired_endpoint"] = name
    audit["pending_curved_gate"] = gate
    return None


def refine(first, scan, node, base, initial, expanded, previous, point, model, support, audit, *, build, fit, metrics, reserve):
    """Build and admit a provisional mask with one original bounded c0 refit."""
    begun = process_time(), perf_counter()
    audit.update(status="untouched", fit_calls=0)
    try:
        if not support["past_distribution_qualified"] or not np.any(expanded & ~initial & ~previous):
            audit["reason"] = "no_qualified_rescue_lost_at_seed"
            return None
        original, reference = first
        eligible, census = qualifying(original, base, point, expanded, initial, previous, support["salvage"])
        audit.update(census, eligible=[row["component"] for row in eligible])
        if len(eligible) != 1:
            audit["reason"] = "no_unique_same_family_slope_only_salvage"
            return None
        if not reserve():
            audit["reason"] = "single_isolated_attempt_already_paid"
            return None
        from blind_joint_finish import rescued_references

        chosen, = eligible
        component = chosen["component"]
        target = chosen["original_nomination"]
        index = target["candidate_index"]
        audit.update(status="reverted", target=chosen)
        spans = sections(base)
        retained_names = {name for name, (_, _, _, sl, _) in spans.items() if previous[sl].any()}
        retained_families = {spans[name][1]["candidate_index"] for name in retained_names}
        accepted = retained_names | {component}
        isolated = isolate_node(original.diagnostic_node, node, accepted)
        active_offers = [row for row in support["salvage"] if row["component"] in accepted]
        prior = rescued_references(reference, active_offers)
        if index not in retained_families:
            prior[index] = float(target["phase_s"])
        keep = previous.copy()
        selected = spans[component][3]
        keep[selected] = expanded[selected]
        proposal, powers, means = build(scan, isolated, keep, point, prior, model)
        if not np.array_equal(keep, proposal.keep):
            raise ValueError("The isolated likelihood changed the supplied observation mask")
        audit.update(curved_before=int(previous.sum()), curved_trial=int(keep.sum()),
                     unrelated_points_excluded=int((expanded & ~keep).sum()), phase_seed_s=prior[index])
        before = float(proposal.calculate(point)["negative_twice_elbo"])
        audit["fit_calls"] = 1
        solution = fit(proposal, point, iterations=48)
        moved = np.asarray(solution["parameters"])
        if moved.shape != (2,) or not np.isfinite(moved).all() or np.any(abs(moved) > scan.search_region.half_width_km + 1e-8):
            audit["reason"] = "original_position_domain"
            return None
        after = float(proposal.calculate(moved)["negative_twice_elbo"])
        audit.update(objective_before=before, objective_after=after, start=point, moved=moved,
                     move_km=float(np.linalg.norm(moved-point)))
        if not np.isfinite([before, after]).all() or after >= before:
            audit["reason"] = "no_strict_same_support_objective_improvement"
            return None
        gates = metrics(proposal, moved)
        reason = provisional_gate(proposal, moved, gates, component, previous, audit)
        if reason is not None:
            audit["reason"] = reason
            return None
        audit.update(status="curved_gate_passed", isolated_branch=True)
        return keep, proposal, powers, means, moved, gates
    except NUMERICAL_ERRORS as error:
        audit.update(status="reverted", reason=f"{type(error).__name__}: {error}")
        return None
    finally:
        audit["isolation_clocks"] = timings(begun)


@contextmanager
def binding():
    import blind_joint_finish as finish
    import blind_joint_repair as repair
    from endpoint_track_repair import binding as endpoint_binding, failing_pair
    from leo.analysis.localization_v3 import conservative_recovery, position

    ordinary_repair = repair.repair_once
    original_propose, original_pair, original_build = finish.propose, finish.finish_pair, finish.build_at
    paid = False

    def reserve():
        nonlocal paid
        if paid:
            return False
        paid = True
        return True

    def ordinary_only(candidate, region, measured):
        if measured.get("isolated_branch"):
            return None, "isolated_branch_failed_endpoint_certificate"
        return ordinary_repair(candidate, region, measured)

    with patch.object(repair, "repair_once", ordinary_only), endpoint_binding():
        endpoint = repair.repair_once

        def paired(scan, node, keep, base, powers, means, model, entries, point, region, measured):
            trial = measured.get("isolated_branch")
            chosen = measured["target"]["component"] if trial else None
            if trial:
                if base.scan is not scan:
                    raise ValueError("The isolated pair uses a different causal scan")
                # The original provisional hook carries the pre-isolation node separately.
                node = base.diagnostic_node
                measured["predictive"] = finish.predictive_details(entries)
                measured["target_predictive"] = [row for row in entries
                                                  if row["norad"] == measured["target"]["original_nomination"]["norad"]]
            result, accepted = original_pair(scan, node, keep, base, powers, means, model, entries, point, region, measured)
            if not trial:
                return result, accepted
            if accepted:
                measured["pair_admission"] = "original_paired_gate"
                return result, True
            failure = failing_pair(result["arms"])
            if failure is None or failure["c0"]["component"] == chosen:
                measured["pair_admission"] = "ordinary_paired_failure"
                return result, False
            measured["paired_before_endpoint"] = measured["finish"]
            repaired, reason = endpoint(result, region, measured)
            if repaired is None:
                measured["endpoint_rejection"] = reason
                return result, False
            measured["finish"] = {arm: finish.readout(row) for arm, row in repaired["arms"].items()}
            measured.update(pair_passes=True, pair_admission="original_paired_gate_after_shared_endpoint")
            return repaired, True

        def propose(*args, **kwargs):
            first = None

            def build(scan, node, keep, point, reference, model):
                nonlocal first
                ready, powers, means = original_build(scan, node, keep, point, reference, model)
                ready.diagnostic_node = node
                if first is None:
                    first = ready, dict(reference)
                return ready, powers, means

            def isolate(scan, node, body, initial, expanded, previous, point, _reference, model,
                        visits, audit, *, build, drop):
                return refine(first, scan, node, body[0], initial, expanded, previous, point, model, visits, audit,
                              build=build, fit=position.fit, metrics=conservative_recovery.retained_metrics, reserve=reserve)

            with patch.object(finish, "build_at", build):
                return original_propose(*args, **kwargs, rescue=isolate)

        with patch.object(finish, "propose", propose), patch.object(finish, "finish_pair", paired):
            yield
