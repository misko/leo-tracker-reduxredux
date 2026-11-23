"""One opt-in position trial before discarding independently salvaged support."""

from time import perf_counter, process_time

import numpy as np

from leo.analysis.localization_v3 import conservative_recovery, position


def independent_support(problem, initial, expanded, nominations):
    """Bind every restored row to the signed independent salvage decision."""
    offers = {row["component"]: row["selected"] for row in nominations if row["selected"] is not None}
    gain = expanded & ~initial
    supported = {}
    for row, section, alias in zip(problem.rows, problem.slices, problem.alias, strict=True):
        restored = np.flatnonzero(gain[section])
        if not len(restored):
            continue
        name = row["component"]
        decision = offers.get(name)
        if (decision is None or len(restored) != decision["points"] or row["candidate_index"] != decision["candidate_index"]
                or row["candidate_norad"] != decision["norad"] or alias != decision["alias"]
                or not np.array_equal(restored, np.arange(decision["start_index"], decision["stop_index"]))):
            return None
        supported[name] = dict(norad=int(decision["norad"]), alias=int(alias), points=len(restored))
    if sum(row["points"] for row in supported.values()) != int(gain.sum()):
        return None
    return supported


def retained_ids(gates):
    ids = [name for track in gates["tracks"] for name in track["observation_ids"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Provisional salvage has duplicate observation ownership")
    return ids


def refine(scan, node, context, initial, expanded, previous, point, reference, model, support, audit, *, build, drop):
    """Return newly qualified common support, or keep the original path intact."""
    audit.update(status="untouched", fit_calls=0)
    if not support["past_distribution_qualified"] or not np.any(expanded & ~initial & ~previous):
        audit["reason"] = "no_qualified_rescue_lost_at_the_seed"
        return None
    base, powers, means = context
    checked = independent_support(base, initial, expanded, support["salvage"])
    if checked is None:
        audit["reason"] = "unbound_signed_salvage_support"
        return None
    start_cpu, start_wall = process_time(), perf_counter()
    audit.update(status="reverted", independently_supported=checked, old_points=int(previous.sum()),
                 provisional_points=int(expanded.sum()), seed_lost_rescue_points=int((expanded & ~initial & ~previous).sum()))
    try:
        before = float(base.calculate(point)["negative_twice_elbo"])
        audit["fit_calls"] = 1
        fit = position.fit(base, point, iterations=48)
        candidate = np.asarray(fit["parameters"])
        if (candidate.shape != (2,) or not np.isfinite(candidate).all()
                or np.any(np.abs(candidate) > scan.search_region.half_width_km + 1e-8)):
            audit["reason"] = "invalid_position"
            return None
        after = float(base.calculate(candidate)["negative_twice_elbo"])
        audit.update(same_support_objective=[before, after], movement_km=float(np.linalg.norm(candidate-point)),
                     position=candidate, stop=fit["stopped"])
        if not np.isfinite([before, after]).all() or after >= before:
            audit["reason"] = "no_strict_same_support_objective_improvement"
            return None
        gates = conservative_recovery.retained_metrics(base, candidate)
        retained, failed = drop(expanded, base.rows, base.slices, gates)
        gained = retained & ~previous & ~initial
        audit.update(postfit_rejected=failed, original_points_lost=int((previous & ~retained).sum()),
                     independently_supported_gain=int(gained.sum()))
        if np.any(previous & ~retained) or not gained.any():
            audit["reason"] = "original_support_lost_or_no_rescued_gain"
            return None
        # The ordinary path may change nuisance terms and powers after dropping
        # rows. Confirm the final subset under those same weights at this point.
        selected = base
        if failed:
            selected, powers, means = build(scan, node, retained, candidate, reference, model)
            gates = conservative_recovery.retained_metrics(selected, candidate)
            audit["subset_rejected"] = [row["component"] for row in gates["tracks"] if not row["compatible"]]
            if audit["subset_rejected"]:
                audit["reason"] = "surviving_subset_fails_original_gate"
                return None
        if len(retained_ids(gates)) != int(retained.sum()):
            raise ValueError("Provisional salvage gates do not cover the retained mask")
        audit.update(status="curved_gate_passed", after_curved=int(retained.sum()))
        return retained, selected, powers, means, candidate, gates
    except (AssertionError, ValueError, np.linalg.LinAlgError) as exc:
        audit["reason"] = f"{type(exc).__name__}: {exc}"
        return None
    finally:
        audit["clocks"] = dict(cpu_s=process_time()-start_cpu, elapsed_s=perf_counter()-start_wall)
