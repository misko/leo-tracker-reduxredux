"""Independent-start adapters for the original six and linear-transfer recipes.

Only observations and this start's zero-initialized discovery are shared. A
matched pair always uses the c0 identity proposals, anchor and fitting budget.
"""

import numpy as np
from compare_dsx01_frame_joint import actual_metrics
from dsx01_cut_linear import bounded_scalar_newton
from dsx01_legacy_jacobian import fit as sparse_fit
from iterate_dsx01_profiled_identity import explore
from map_dsx01_clean_legacy import make_problem
from map_dsx01_clean_linear import nominations_for
from map_dsx01_clean_region import factory
from probe_dsx01_cut_linear import CutScore
from report_dsx01_cut_linear import linear_metrics
from report_dsx01_model_iterations import nominated_metrics
from run_dsx01_clean_region import reference_state


def paired_aliases(problems, aliases):
    """Write through the legacy wrapper; shadowing its alias is insufficient."""
    for p in problems.values():
        p.problem.alias = list(aliases)


def gate_summary(metrics, *, modern=False):
    rows = metrics["tracks"]
    return dict(
        associated_points=sum(r["points"] for r in rows if r["compatible"]),
        associated_tracks=sum(bool(r["compatible"]) for r in rows),
        residual_rms_hz=metrics[
            "accepted_native_rms_hz" if modern else "all_curved_native_rms_hz"
        ],
        track_associations=[
            dict(
                component=r["component"],
                norad=int(r.get("norad", 0)),
                points=r["points"],
                compatible=bool(r["compatible"]),
            )
            for r in rows
        ],
    )


def run_legacy_recipe(scan, sigma, discovery, method, *, iterations=24, rounds=2):
    del sigma
    anchor = np.asarray(discovery["start_east_north_km"], float)
    state = reference_state(discovery["seed"]["state"])
    records = []
    for number in range(rounds):
        seed, detail = explore(scan, state, anchor, method, compact_update=False)
        problems = {a: make_problem(scan, seed, method, a, anchor) for a in ("c0", "fitted_c")}
        aliases = list(problems["c0"].alias)
        paired_aliases(problems, aliases)
        arms = {}
        for arm, p in problems.items():
            fit = sparse_fit(p, p.initial, iterations=iterations)
            point = np.asarray(fit["parameters"][:2])
            state_arm = p.association_state(fit["parameters"])
            metrics = nominated_metrics(
                scan,
                dict(
                    method=method,
                    arm=arm,
                    fit=dict(
                        rows=p.rows,
                        state=state_arm,
                        aliases=p.alias,
                        east_north_km=point,
                        fits=[fit],
                    ),
                ),
                problem_factory=lambda *args, p=p: p,
            )
            arms[arm] = dict(
                fit=fit,
                endpoint_east_north_km=point,
                state=state_arm,
                aliases=p.alias,
                rows=p.rows,
                **gate_summary(metrics),
            )
        records.append(
            dict(round=number, anchor=anchor, proposals=detail, arms=arms)
        )
        anchor = np.asarray(arms["c0"]["endpoint_east_north_km"])
        state = reference_state(arms["c0"]["state"])
    return dict(
        arms=arms,
        rounds=records,
        matched_c0_fitted_c=True,
        satellite_assignments_refreshed_between_rounds=True,
        solver="sparse derivatives of unchanged legacy residual objective",
    )


def run_linear_recipe(scan, sigma, parent, variant, *, iterations=24):
    node, reference = parent["final_node"], parent["final_reference"]
    problems = {
        a: factory(scan, node, sigma, "normal", a == "fitted_c", reference=reference)
        for a in ("c0", "fitted_c")
    }
    parent_fit = parent["arms"]["c0"]["fit"]
    point = np.asarray(parent_fit["parameters"][:2])
    p = problems["c0"]
    metrics = actual_metrics(
        p,
        dict(parent_fit, rows=p.rows, aliases=p.alias, east_north_km=point, fits=[parent_fit]),
        "c0",
        point,
    )
    nominations = nominations_for(p, point, metrics)
    candidates = [n for n in nominations if n["accepted"]]
    strict = {r["component"] for r in linear_metrics(p, point, candidates) if r["compatible"]}
    selected = [
        dict(
            n,
            accepted=n["accepted"]
            and (not variant.startswith("white") or n["component"] in strict),
        )
        for n in nominations
    ]
    kind = (
        "shape"
        if variant.endswith("shape")
        else "joint"
        if variant.startswith("white")
        else variant
    )
    arms = {}
    for arm, p in problems.items():
        score = CutScore(p, selected, kind)
        fit = bounded_scalar_newton(
            lambda x, s=score: s.score(x)["total"], point, iterations=iterations
        )
        x = np.asarray(fit["parameters"])
        cm = actual_metrics(
            p,
            dict(
                fit,
                state=p.state(x),
                rows=p.rows,
                aliases=p.alias,
                east_north_km=x,
                fits=[fit],
            ),
            arm,
            x,
        )
        lm = linear_metrics(p, x, score.selected)
        summary = gate_summary(cm, modern=True)
        summary["associated_points"] += sum(r["points"] for r in lm if r["compatible"])
        summary["associated_tracks"] += sum(bool(r["compatible"]) for r in lm)
        summary["track_associations"] += [
            dict(
                component=r["component"],
                norad=r["norad"],
                points=r["points"],
                compatible=r["compatible"],
            )
            for r in lm
        ]
        arms[arm] = dict(
            fit=fit,
            endpoint_east_north_km=x,
            aliases=p.alias,
            state=p.state(x),
            linear_nominated_points=sum(n["points"] for n in score.selected),
            **summary,
        )
    return dict(
        arms=arms,
        rounds=[],
        curved_parent_rounds=parent["rounds"],
        linear_nomination_anchor=point,
        fresh_same_start_curved_parent=True,
        calibration_from_curves_only=True,
        matched_c0_fitted_c=True,
        linear_nominations=nominations,
    )
