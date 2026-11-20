"""Estimate a signed position interval from disjoint compact subscans."""

import numpy as np

from .edge_evidence import ARMS
from .v5_secant_fit import STOP_KM, bounded_secant

BLOCK_S = 12
SUBSCANS = 4
RADIUS_KM = 6.0
T90 = 2.3533634348  # One-sided 95% Student-t quantile with three degrees of freedom.


def time_groups(times):
    return np.floor(np.asarray(times) / BLOCK_S).astype(np.int64) % SUBSCANS


def interval(inward_km):
    inward = np.asarray(inward_km, float)
    if len(inward) != SUBSCANS or not np.isfinite(inward).all():
        return dict(state="insufficient", subscan_inward_km=inward.tolist())
    middle = float(inward.mean())
    spread = T90 * float(inward.std(ddof=1)) / np.sqrt(SUBSCANS)
    low, high = middle - spread - STOP_KM, middle + spread + STOP_KM
    state = "inside" if low > 0 else "outside" if high < 0 else "weak"
    return dict(
        state=state,
        subscan_inward_km=inward.tolist(),
        mean_inward_km=middle,
        interval_km=[low, high],
    )


def evaluate(ctx, triplet):
    from leo.analysis.localization_v3.history_position import make_problem

    inside, face, outside = triplet
    normal = (inside - outside) / np.linalg.norm(inside - outside)
    groups = time_groups(ctx["base"].flat_times)
    owners = np.asarray(ctx["base"].labels)[ctx["base"].flat_labels]
    keep = np.asarray(ctx["keep"], bool)
    masks = [(groups == i) & keep for i in range(SUBSCANS)]
    if any(np.unique(owners[mask]).size < 4 or mask.sum() < 40 for mask in masks):
        return {
            arm: dict(state="insufficient", subscan_points=[int(m.sum()) for m in masks])
            for arm in ARMS
        }
    references = np.clip(ctx["means"], -15, 15)
    weights = np.ones(len(ctx["powers"]))
    rows = {}
    for arm in ARMS:
        signed, rms, active_box, stops = [], [], [], []
        for mask in masks:
            p = make_problem(
                ctx["scan"],
                ctx["node"],
                mask,
                arm,
                references,
                weights,
                ctx["means"],
                ctx["model"]["multiplier"],
                ctx["model"]["nu"],
            )
            fit = bounded_secant(
                p.residual, face, face - RADIUS_KM, face + RADIUS_KM, iterations=12, step=STOP_KM
            )
            point = fit["parameters"]
            stops.append(fit["stopped"])
            displacement = point - face
            signed.append(float(displacement @ normal))
            active_box.append(bool(np.max(abs(displacement)) >= RADIUS_KM - STOP_KM))
            r = p.calculate(point)["conditional_residual_hz"][mask]
            rms.append(float(np.sqrt(np.mean(r**2))))
        result = interval(signed)
        if any(active_box):
            result["state"] = "halo_bound"
        elif "iteration_budget" in stops:
            result["state"] = "solver_unresolved"
        rows[arm] = dict(
            result,
            subscan_rms_hz=rms,
            subscan_points=[int(m.sum()) for m in masks],
            subscan_halo_bound=active_box,
            subscan_stop=stops,
        )
    return rows
