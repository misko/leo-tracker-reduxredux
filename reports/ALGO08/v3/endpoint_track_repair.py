"""Recover one curved fragment by testing either chronological edge on both arms."""

from contextlib import contextmanager
from functools import wraps
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np


ARMS = ("c0", "fitted_c")
MAXIMUM_STEP_Z = 4.0  # The released polynomial noise screen.


def failing_pair(arms):
    if set(arms) != set(ARMS):
        return None
    rows = {}
    for arm in ARMS:
        record = arms[arm]
        failures = [row for row in record["gates"]["tracks"] if not row["compatible"]]
        if len(failures) != 1 or any(not row["compatible"] for row in record["linear_gates"]):
            return None
        failure = failures[0]
        conditional = failure["conditional_residual_gate"]
        step = conditional["diagnostics"]["maximum_step_z"]
        if conditional["compatible"] or not np.isfinite(step) or step <= MAXIMUM_STEP_Z:
            return None
        rows[arm] = failure
    first, second = (rows[arm] for arm in ARMS)
    if first["component"] == second["component"] and first["observation_ids"] == second["observation_ids"]:
        return rows
    return None


def trim_choices(fragment, ids, gate=None):
    from fragment_gate_cross import local_gate, scope
    from leo.analysis.localization_v3.conservative_recovery import selected_supports
    from leo.analysis.localization_v3.tracks import active_curvature

    if gate is None:
        gate = local_gate
    indices = scope(fragment, ids)
    n = len(indices)
    if (not np.array_equal(indices, np.flatnonzero(fragment["mask"]))
            or np.any(np.diff(fragment["times"][indices]) <= 0)):
        raise ValueError("Curved fragment differs from the original chronological support")
    allowed = selected_supports(n)
    choices = {}
    for removed, bounds in (("first", (1, n)), ("last", (0, n-1))):
        if bounds not in allowed:
            continue
        a, b = bounds
        take = indices[a:b]
        track = dict(times=fragment["times"][take], values=fragment["raw_hz"][take])
        if active_curvature(track):
            choices[removed] = gate(fragment, ids[a:b])
    return choices


def unique_endpoint(choices):
    witnesses = [[name for name, gate in choices[arm].items() if gate["compatible"]] for arm in ARMS]
    first, second = witnesses
    if len(first) == 1 and first == second:
        return first[0]
    return None


def frozen_choices(candidate, failures):
    from fragment_gate_cross import local_gate, sections, state
    from leo.analysis.localization_v3 import event_position

    scan, node, keep, powers, means, model, entries = (candidate[key] for key in (
        "scan", "node", "keep", "powers", "means", "model", "entries"))
    masks, checks = {}, {}
    for arm in ARMS:
        failed = failures[arm]
        component, ids = failed["component"], failed["observation_ids"]
        record = candidate["arms"][arm]
        problem = event_position.make_event_problem(scan, node, keep, arm, record["phase_reference"],
                                                    powers, means, model, [])
        event_position.attach_event_predictive(problem, entries, powers)
        event_position.cached(problem)
        point = record["endpoint_east_north_km"]
        fragment = state(problem, point, {component})[component]
        full = local_gate(fragment, ids)
        step = full["conditional_residual_gate"]["diagnostics"]["maximum_step_z"]
        recorded = failed["conditional_residual_gate"]["diagnostics"]["maximum_step_z"]
        if full["compatible"] or abs(step-recorded) > 1e-10:
            raise ValueError("Frozen full-fragment gate disagrees with its original arm")
        _, _, _, sl, _ = sections(problem)[component]
        active = np.flatnonzero(fragment["mask"])
        masks[arm] = {"first": sl.start+int(active[0]), "last": sl.start+int(active[-1])}
        checks[arm] = dict(full=full, endpoints=trim_choices(fragment, ids))
    if masks["c0"] != masks["fitted_c"]:
        raise ValueError("Both calibration arms must use the same retained mask")
    return masks["c0"], checks


def refit_pair(candidate, keep, region, audit):
    from blind_joint_finish import arm_finish, readout
    from leo.analysis.localization_v3.history_policy import pair_passes

    scan, node, powers, means, model, entries = (candidate[k] for k in (
        "scan", "node", "powers", "means", "model", "entries"))
    labels = sorted({row["candidate_index"] for row in node["seed"]["rows"]})
    results = {}
    for arm in ARMS:
        prior = candidate["arms"][arm]
        seed = prior["endpoint_east_north_km"]
        phases = np.clip(prior["state"]["phases"][labels], -15., 15.)
        results[arm] = arm_finish(scan, node, keep, arm, phases, powers, means, model, entries, seed)
    audit["finish"] = {arm: readout(record) for arm, record in results.items()}
    if not pair_passes(results, include_linear=True, half_width_km=region.half_width_km):
        return None
    return dict(candidate, keep=keep, arms=results)


def try_trim(candidate, failures, region, audit):
    spans, checks = frozen_choices(candidate, failures)
    audit["frozen"] = checks
    end = unique_endpoint({arm: check["endpoints"] for arm, check in checks.items()})
    if end is None:
        audit.update(status="rejected", reason="no_unique_shared_endpoint")
        return None
    kept = candidate["keep"].copy()
    kept[spans[end]] = False
    shared = failures["c0"]
    ids = shared["observation_ids"]
    audit.update(endpoint=end, dropped_id=ids[0 if end == "first" else -1],
                 component=shared["component"], curve_points_before=len(ids), refit_calls=1)
    result = refit_pair(candidate, kept, region, audit)
    if result is None:
        audit.update(status="rejected", reason="original_paired_gate_after_refit")
        return None
    audit["status"] = "accepted"
    return result


@contextmanager
def binding():
    from blind_joint_repair import repair_once

    attempted = False

    @wraps(repair_once)
    def repair(candidate, region, measured):
        nonlocal attempted
        failed = failing_pair(candidate["arms"])
        if failed is not None and not attempted:
            attempted = True
            audit = measured["endpoint_trim"] = {"refit_calls": 0}
            cpu, wall = process_time(), perf_counter()
            try:
                result = try_trim(candidate, failed, region, audit)
                if result is not None:
                    return result, None
            except (AssertionError, ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
                audit.update(status="rejected", reason=f"{type(error).__name__}: {error}")
            finally:
                audit.update(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)
        return repair_once(candidate, region, measured)

    with patch("blind_joint_repair.repair_once", repair):
        yield
