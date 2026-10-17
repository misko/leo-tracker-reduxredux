"""DSX-C: deterministic complete-state basins under one shared training budget.

No candidate identities or observation CFOs are inspected here. The unchanged
masked model and common refitter own likelihood, constraints and strict audit.
"""

import math
import time

import numpy as np


class BudgetContractError(RuntimeError):
    """A common-port accounting violation must stop the whole experiment."""


def basins(context):
    """Six prespecified starts, same bank/q/calibration dimensions and priors."""
    v, n = np.asarray(context.vector, float).copy(), np.asarray(context.nuisance, float).copy()
    model = context.model
    radius = float(context.prior.radius_km)
    if (v.ndim != 1 or len(v) < 8 or n.ndim != 1 or not np.isfinite(v).all()
            or not np.isfinite(n).all() or np.linalg.norm(v[:2]) > radius+1e-9):
        raise ValueError("finite complete seed inside the original geographic prior required")
    if context.fixed_c:
        v[6] = 0.
    rows = [("original", v.copy(), n.copy())]
    # Convex combinations of feasible geographic points stay inside the SAME
    # original prior disk. These are not station coordinates or score-derived.
    distance = min(15., .1*radius)
    blend = distance/radius
    diagonal = np.array([1., 1.])/np.sqrt(2)
    for sign, name in ((1, "position-ne"), (-1, "position-sw")):
        vv = v.copy()
        vv[:2] = (1-blend)*v[:2]+sign*distance*diagonal
        rows.append((name, vv, n.copy()))
    # RX intercept alternatives on the existing folded frequency circle;
    # original clock reset is a complete calibration basin, not a new term.
    from leo.analysis.regional_position_score import ALIAS_HZ
    for sign, name in ((1, "calibration-plus"), (-1, "calibration-minus")):
        vv, nn = v.copy(), n.copy()
        vv[[2, 4]] += sign*ALIAS_HZ/8
        nn[:model.clock_count] = 0.
        rows.append((name, vv, nn))
    # Convex timing alternative in the existing common/zero-sum coordinates.
    # Full times are metadata only; no withheld CFO is accessed.
    tau = v[7]+model.basis@v[8:]
    lower = max(-20., float(model.bank.nodes_s[0]-model.observations.times_s.min()))
    upper = min(20., float(model.bank.nodes_s[-1]-model.observations.times_s.max()))
    if not lower < 0 < upper:
        raise ValueError("original interpolation support must straddle zero")
    amplitude = min(.5, -lower/2, upper/2)
    target = amplitude*np.cos(np.arange(len(tau))+.3)
    changed = .8*tau+.2*target
    vv = v.copy()
    vv[7] = changed.mean()
    vv[8:] = model.basis.T@(changed-vv[7])
    rows.append(("relative-timing", vv, n.copy()))
    return rows


def fit(context, *, max_evaluations=180, max_seconds=120):
    """Select best feasible research state; strict acceptance remains explicit."""
    from common import refit

    if (type(max_evaluations) is not int or max_evaluations < 1
            or not math.isfinite(max_seconds) or max_seconds <= 0):
        raise ValueError("positive finite total budget required")
    begun = time.monotonic()
    deadline = min(begun+max_seconds, getattr(context, "deadline", math.inf))
    starts = basins(context)
    # Fixed quotas prevent an early basin consuming later basin allocations.
    # Empty quotas are reported, not executed; no uncounted seed/ranking calls.
    quotas = [max_evaluations//len(starts)+(i < max_evaluations % len(starts))
              for i in range(len(starts))]
    records, outcomes, used = [], [], 0
    for index, ((label, vector, nuisance), quota) in enumerate(zip(starts, quotas, strict=True)):
        remaining = deadline-time.monotonic()
        row = dict(basin=label, quota=int(quota), seed_vector=vector.tolist(),
                   seed_nuisance=nuisance.tolist())
        if not quota or remaining <= 0:
            row.update(evaluations=0, accepted=False, reason="total-budget-exhausted")
            records.append(row)
            continue
        seconds = remaining/(len(starts)-index)
        try:
            result = refit(context, vector, nuisance, max_evaluations=int(quota),
                           max_seconds=seconds, fixed_c=bool(context.fixed_c))
            diagnostics = dict(result["diagnostics"])
            calls = diagnostics["evaluations"]
            if type(calls) is not int or not 0 <= calls <= quota:
                raise BudgetContractError("common refit violated its declared objective-call quota")
            used += calls
            row.update(diagnostics)
            objective = diagnostics.get("objective")
            if (objective is not None and math.isfinite(objective)
                    and np.isfinite(result["vector"]).all()
                    and np.isfinite(result["nuisance"]).all()):
                outcomes.append((index, result))
        except (ValueError, TimeoutError, RuntimeError) as error:
            if isinstance(error, BudgetContractError):
                raise
            # An exception without a terminal count consumes its whole reserved
            # quota. Never invent zero objective cost or automatically retry.
            used += quota
            row.update(evaluations=int(quota), accepted=False,
                       reason=f"{type(error).__name__}: {error}", accounting="reserved-upper-bound")
        records.append(row)
    accepted = [(i, r) for i, r in outcomes if r["diagnostics"].get("accepted") is True]
    selected = min(outcomes, key=lambda pair: (pair[1]["diagnostics"]["objective"], pair[0])) \
        if outcomes else None
    strict = min(accepted, key=lambda pair: (pair[1]["diagnostics"]["objective"], pair[0])) \
        if accepted else None
    best_feasible = min((r["diagnostics"]["objective"] for _, r in outcomes), default=None)
    diagnostics = dict(model="DSX-C", method="six-deterministic-complete-state-basins-v1",
        evaluations=used, maximum_evaluations=max_evaluations, records=records,
        accepted=False, elapsed_seconds=time.monotonic()-begun,
        selection="minimum feasible training objective; nonstationary remains research only",
        source_id=context.source_id, fixed_c=bool(context.fixed_c),
        evaluation_accounting=("reserved upper bound for unreturned failures"
            if any(r.get("accounting") == "reserved-upper-bound" for r in records) else "actual"),
        best_feasible_objective=best_feasible,
        strict_objective=strict[1]["diagnostics"]["objective"] if strict else None,
        strict_basin=starts[strict[0]][0] if strict else None)
    if selected is None:
        diagnostics.update(reason="no finite returned basin", objective=None, selected_basin=None)
        return dict(vector=np.asarray(context.vector).copy(),
                    nuisance=np.asarray(context.nuisance).copy(),
                    diagnostics=diagnostics)
    index, result = selected
    diagnostics.update(objective=result["diagnostics"]["objective"],
        stationarity=result["diagnostics"].get("stationarity"), selected_basin=starts[index][0],
        accepted=result["diagnostics"].get("accepted") is True,
        strict_search_gap=(strict[1]["diagnostics"]["objective"]-best_feasible) if strict else None)
    return dict(vector=np.asarray(result["vector"]).copy(),
                nuisance=np.asarray(result["nuisance"]).copy(), diagnostics=diagnostics)
