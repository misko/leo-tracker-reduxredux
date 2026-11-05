"""Owned final-stage likelihood, adopted native evidence and RF influence trigger.

The final reassociation stage preserves its own frozen contraction order. Its
position domain comes from the scan; evaluation coordinates are never inputs.
"""

from copy import deepcopy

import numpy as np

from leo.analysis.localization_v3.conditional_satellite import attach_conditional_satellite_refresh
from leo.analysis.localization_v3.event_position import cached, make_event_problem
from leo.analysis.localization_v3.new_family import NewFamily
from leo.analysis.localization_v3.recovery_inclusion import attach_recovery_predictive
from leo.analysis.localization_v3.residual_position import add_target, prediction_scan
from leo.analysis.localization_v3.residual_position import family_score as residual_family_score

ARMS = ("c0", "fitted_c")


def family_score(families, context, problem, x, details=False):
    # Frozen ALGO06 trials use direct contractions; frozen final ALGO07 uses
    # optimized contractions. Preserve each stage's numerical schedule.
    return residual_family_score(families, context, problem, x, details, optimize_contractions=True)


def build(context, arm, reference, omit=None, phase_scale=1.0):
    keep = context["keep"].copy()
    base = context["problems"][arm][0]
    for row, sl in zip(base.rows, base.slices, strict=True):
        if row["candidate_norad"] == omit:
            keep[sl] = False
    entries = [entry for entry in context["entries"] if entry["norad"] != omit]
    kwargs = (
        {"base_problem_factory": context["problem_factory"]} if "problem_factory" in context else {}
    )
    problem = make_event_problem(
        context["scan"],
        context["node"],
        keep,
        arm,
        reference,
        context["powers"],
        context["means"],
        dict(context["model"], multiplier=context["model"]["multiplier"] * phase_scale),
        [],
        **kwargs,
    )
    attach_recovery_predictive(problem, entries, context["powers"])
    keys = context.get("conditional_components", ())
    labels = sorted({entry["candidate_index"] for entry in entries if entry["component"] in keys})
    if labels:
        attach_conditional_satellite_refresh(problem, entries, context["powers"], labels)
    return cached(problem), dict(
        context,
        entries=entries,
        families=[family for family in context["families"] if family.entries[0]["norad"] != omit],
    )


def objective(problem, context, x):
    calculation = problem.calculate(x)
    return float(
        calculation["negative_twice_elbo"]
        + family_score(context["families"], context, problem, x)
        + np.sum(np.minimum(0, calculation["elevation"][problem.keep]) ** 2) / 4
    )


def adopt_additional(
    context_factory, arms, owners, selection, recovery, screen, catalogue, observations
):
    """Restore the chosen additional likelihood and independently audit ownership.

    Rejected/no-addition trials retain the selected state exactly. A qualified
    trial supplies its complete saved numerical result, never just coordinates.
    """
    context = context_factory()
    context["problems"] = dict(context["problems"])
    selected_arms, selected_owners = deepcopy(arms), deepcopy(owners)
    conditional = []
    if selection and selection["kind"] in ("gap_conditional", "shared_family"):
        protocol = selection["trial"]["protocol"]
        if selection["kind"] == "gap_conditional" or protocol.get("conditional_satellite_refresh"):
            conditional = [entry["component"] for entry in protocol["targets"]]
    context["conditional_components"] = tuple(conditional)
    decision = recovery["decisions"]["72h_30s"]
    replay = dict(pre_recovery=context["replay_checks"], recovery=deepcopy(decision))
    if decision["status"] == "qualified":
        trial = recovery["trials"][decision["trial"]]
        if trial["status"] != "qualified" or set(trial["arms"]) != set(ARMS):
            raise ValueError("Qualified additional trial is incomplete")
        for pair in (recovery["control"], trial["arms"]):
            if set(pair) != set(ARMS) or not all(
                row["all_checked_gates_pass"] for row in pair.values()
            ):
                raise ValueError(
                    "Qualified additional trial requires both control and candidate arms"
                )
        target = next(
            t for t in screen["targets"] if t["source"]["fragment_id"] == decision["source"]
        )
        summary = next(s for s in target["summaries"] if s["policy"] == "72h_30s")
        winner = summary["arms"]["c0"]["folds"]["full"]["winner"]
        entry = add_target(context, target["source"], winner, catalogue, observations, owners)
        if entry != trial["entry"]:
            raise ValueError("Additional native recovery entry mismatch")
        family = NewFamily(
            prediction_scan(context["scan"], 30),
            [entry],
            context["model"],
            phase_step=0.05,
            phase_limit_s=30,
            allow_uncalibrated_label=True,
        )
        context["families"] = context["families"] + [family]
        replay["algo06"] = {}
        for arm in ARMS:
            row = trial["arms"][arm]
            x = np.asarray(row["endpoint_east_north_km"])
            problem, _ = build(context, arm, np.asarray(row["phase_reference"]))
            delta = float(
                problem.calculate(x)["negative_twice_elbo"]
                + family_score(context["families"], context, problem, x)
                - row["negative_twice_elbo"]
            )
            if not np.isfinite(delta) or abs(delta) > 1e-4:
                raise ValueError(f"Additional full replay mismatch {arm} {delta}")
            context["problems"][arm] = problem, x
            selected_arms[arm] = deepcopy(row)
            for identity in entry["observation_ids"]:
                if identity in selected_owners[arm]:
                    raise ValueError("Duplicate additional owner")
                selected_owners[arm][identity] = entry["norad"]
            replay["algo06"][arm] = dict(
                objective_difference=delta, added_points=len(entry["observation_ids"])
            )
    replay["rebuilt"] = {}
    for arm, (problem, x) in context["problems"].items():
        rebuilt, _ = build(context, arm, problem.reference)
        delta = objective(rebuilt, context, x) - objective(problem, context, x)
        if not np.isfinite(delta) or abs(delta) > 1e-4:
            raise ValueError(f"Rebuilt baseline objective mismatch {arm}: {delta}")
        replay["rebuilt"][arm] = delta
    return dict(context=context, arms=selected_arms, owners=selected_owners, replay=replay)


def active_ids(context):
    return (
        {int(context["scan"].norads[j]) for j in context["problems"]["fitted_c"][0].labels}
        | {entry["norad"] for entry in context["entries"]}
        | {entry["norad"] for family in context["families"] for entry in family.entries}
    )


def derivatives(function, x, h=0.05):
    eye = np.eye(2) * h
    value = function(x)
    gradient, hessian = np.zeros(2), np.zeros((2, 2))
    for i in range(2):
        plus, minus = function(x + eye[i]), function(x - eye[i])
        gradient[i] = (plus - minus) / (2 * h)
        hessian[i, i] = (plus - 2 * value + minus) / h**2
    hessian[0, 1] = hessian[1, 0] = (
        function(x + eye[0] + eye[1])
        - function(x + eye[0] - eye[1])
        - function(x - eye[0] + eye[1])
        + function(x - eye[0] - eye[1])
    ) / (4 * h * h)
    return gradient, hessian


def rank_families(context):
    """Original RF influence trigger; no geographic truth or omission Hessians."""
    rows, eye = {}, np.eye(2) * 0.05
    for arm, (problem, x) in context["problems"].items():
        gradient, hessian = derivatives(
            lambda v, problem=problem: objective(problem, context, v), x
        )
        numbers = {
            row["candidate_norad"]
            for row, sl in zip(problem.rows, problem.slices, strict=True)
            if problem.keep[sl].any()
        }
        for norad in sorted(numbers):
            reduced, omitted = build(context, arm, problem.reference, omit=norad)
            reduced_gradient = np.array(
                [
                    (objective(reduced, omitted, x + v) - objective(reduced, omitted, x - v)) / 0.1
                    for v in eye
                ]
            )
            displacement = float(
                np.linalg.norm(np.linalg.pinv(hessian) @ (reduced_gradient - gradient))
            )
            entries = [
                (row, sl)
                for row, sl in zip(problem.rows, problem.slices, strict=True)
                if row["candidate_norad"] == norad and problem.keep[sl].any()
            ]
            item = rows.setdefault(
                norad,
                dict(
                    norad=norad,
                    rank_score=0.0,
                    arms={},
                    points=sum(int(problem.keep[sl].sum()) for _, sl in entries),
                    tracks=len(entries),
                ),
            )
            item["arms"][arm] = dict(
                local_displacement_km=displacement, hessian_eigenvalues=np.linalg.eigvalsh(hessian)
            )
            item["rank_score"] += displacement
    result = sorted(rows.values(), key=lambda row: (-row["rank_score"], row["norad"]))
    selected = [
        row["norad"]
        for row in result
        if row["rank_score"] >= 0.5 and row["points"] >= 30 and row["tracks"] >= 2
    ][:2]
    return result, selected
