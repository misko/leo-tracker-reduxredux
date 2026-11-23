"""Use the original qualified curved pair to initialize one named predictive refit."""

from contextlib import contextmanager
from time import perf_counter, process_time
from unittest.mock import patch


ARMS = ("c0", "fitted_c")


def now():
    return process_time(), perf_counter()


def elapsed(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def initial_states(scan, node, curved):
    import numpy as np

    labels = sorted({row["candidate_index"] for row in node["seed"]["rows"]})
    if not labels or any(index < 0 or index >= len(scan.norads) for index in labels):
        raise ValueError("The qualified curved state has no original family-labelled phase coordinates")
    seeds = {}
    for arm in ARMS:
        record = curved[arm]
        x = np.asarray(record["endpoint_east_north_km"], float)
        before = np.asarray(record["state"]["phases"], float)
        if (x.shape != (2,) or not np.isfinite(x).all() or np.any(abs(x) > scan.search_region.half_width_km + 1e-8)
                or before.shape != (len(scan.norads),) or not np.isfinite(before[labels]).all()):
            raise ValueError("The earlier curved site or phase state is outside the original fit domain")
        seeds[arm] = (x.copy(), np.clip(before[labels], -15., 15.))
    return labels, seeds


def settled(record):
    import numpy as np

    return bool(np.isfinite([record["RMS_hz"], record["negative_twice_elbo"], record["final_phase_change_s"]]).all()
                and record["final_phase_change_s"] <= .01
                and record["history"][-1]["movement_km"] <= .020)


def note(record):
    return dict(endpoint=record["endpoint_east_north_km"], normalized_objective=record["negative_twice_elbo"],
                refreshes=len(record["history"]), final_phase_change_s=record["final_phase_change_s"],
                final_step_km=record["history"][-1].get("movement_km"))


def try_warm(scan, node, keep, powers, means, model, entries, curved, audit):
    import numpy as np
    from blind_joint_finish import arm_finish
    from leo.analysis.localization_v3.history_policy import pair_passes

    start = now()
    audit["attempted"] = True
    try:
        try:
            labels, phases = initial_states(scan, node, curved)
            audit["source"] = "earlier-qualified-named-curved-pair"
            audit["initial"] = {arm:dict(east_north_km=x, phase_s=phase) for arm,(x,phase) in phases.items()}
            audit["phase_norads_in_order"] = [int(scan.norads[j]) for j in labels]
        finally:
            audit["initialization"] = elapsed(start)
        result = {}
        audit["warm_arm_clocks"] = {}
        for arm, (x, phase) in phases.items():
            begin = now()
            try:
                result[arm] = arm_finish(scan, node, keep, arm, phase, powers, means, model, entries, x)
            finally:
                audit["warm_arm_clocks"][arm] = elapsed(begin)
        audit["warm_arms"] = {a:note(value) for a,value in result.items()}
        if not all(settled(row) for row in result.values()):
            audit["fallback_reason"] = "original_warm_stability_threshold"
            return None
        if not pair_passes(result, include_linear=True, half_width_km=scan.search_region.half_width_km):
            audit["fallback_reason"] = "original_full_paired_gate"
            return None
        audit["used"] = True
        return result
    except (ValueError, AssertionError, FloatingPointError, np.linalg.LinAlgError) as exc:
        audit["fallback_reason"] = f"{type(exc).__name__}: {exc}"
        return None
    finally:
        audit["warm_attempt"] = elapsed(start)


@contextmanager
def linear_policy(enabled, audit):
    """Choose both arms before returning either to the original family policy."""
    from leo.analysis.localization_v3 import history_policy as named

    original_curved, original_linear = named.history_fit, named.linear_refit
    state = {}

    def history_fit(scan, node, keep, powers, means, model, **kwargs):
        start = now()
        result = original_curved(scan, node, keep, powers, means, model, **kwargs)
        row = dict(curved_clock=elapsed(start), attempted=False, used=False, cold_arms={})
        audit.append(row)
        state.clear()
        state.update(scan=scan, node=node, keep=result[1], powers=powers, means=means, model=model,
                     curved=result[0], audit=row)
        return result

    def linear_refit(scan, node, keep, powers, means, model, arm, entries):
        if any(state[key] is not value for key,value in zip(("scan", "node", "keep", "powers", "means", "model"),
                                                           (scan, node, keep, powers, means, model), strict=True)):
            raise ValueError("Predictive fit did not receive the current qualified curve likelihood")
        row = state["audit"]
        if "entries" not in state:
            if arm != ARMS[0]:
                raise ValueError("The original paired predictive call order changed")
            state["entries"] = entries
            row.update(offered_curved_points=int(keep.sum()), offered_predictive_points=sum(e["points"] for e in entries))
            state["warm"] = try_warm(scan, node, keep, powers, means, model, entries, state["curved"], row) if enabled and entries else None
        elif arm != ARMS[1] or entries is not state["entries"]:
            raise ValueError("Named predictive arms must share the original offered roster in order")
        if state["warm"] is not None:
            return state["warm"][arm]
        stamp = now()
        linear = original_linear(scan, node, keep, powers, means, model, arm, entries)
        row["cold_arms"][arm] = dict(**note(linear), clock=elapsed(stamp))
        return linear

    with (patch.object(named, "history_fit", history_fit), patch.object(named, "linear_refit", linear_refit)):
        yield
