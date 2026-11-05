"""Final guarded identity repair with matched history, evidence and fit budgets."""

from copy import deepcopy

import numpy as np

from leo.analysis.localization_v3.reassociation_context import ARMS, active_ids, objective
from leo.analysis.localization_v3.reassociation_fit import fit_rows, paired
from leo.analysis.localization_v3.reassociation_history import complete_history
from leo.analysis.localization_v3.reassociation_policy import (
    POLICY,
    fit_rows_complete,
    score_record,
    select,
)
from leo.analysis.localization_v3.reassociation_remap import remap


def baseline_from_selected(arms, owners):
    """Original compact endpoint authority; evaluation error stays outside inference."""
    return {
        arm: dict(
            x=deepcopy(arms[arm]["endpoint_east_north_km"]),
            error_m=None,
            objective=arms[arm]["negative_twice_elbo"],
            associated=len(owners[arm]),
            rms_hz=None,
        )
        for arm in ARMS
    }


def fallback(baseline, status, **metadata):
    return dict(
        policy=POLICY,
        selected=None,
        final=deepcopy(baseline),
        review=[],
        baseline=deepcopy(baseline),
        execution_status=status,
        production_modified=False,
        **metadata,
    )


def recover(
    context,
    owners,
    baseline,
    admission,
    catalogue,
    scan_receipt,
    collect_history,
    *,
    on_fit=None,
    on_record=None,
    on_selected=None,
):
    """Finish admitted proposals; a partial fit always retains the exact baseline.

    No sequential adoption: every hypothesis starts from the same incumbent.
    This owns scientific decisions only; process limits and publication are
    application concerns. Callbacks receive isolated completed checkpoints.
    """
    for arm, (problem, x) in context["problems"].items():
        if not np.array_equal(x, np.asarray(baseline[arm]["x"])):
            raise ValueError("Published baseline coordinate replay mismatch")
        delta = objective(problem, context, x) - baseline[arm]["objective"]
        if not np.isfinite(delta) or abs(delta) > 1e-4:
            raise ValueError("Published baseline RF objective replay mismatch")
        if len(owners[arm]) != baseline[arm]["associated"]:
            raise ValueError("Published native ownership replay mismatch")
    targets = admission["targets"]
    if admission["status"] == "propagation_fallback":
        return fallback(
            baseline,
            "propagation_fallback",
            targets=targets,
            propagation_failures=admission["propagation_failures"],
            records=[],
            guards={},
            history=None,
        )
    if admission["status"] != "screened":
        raise ValueError("Complete causal screening required")
    records, history, historical = [], None, None
    controls_by_target, fits_by_proposal = {}, {}
    candidate_contexts, candidate_states = {}, {}
    ledger = catalogue["elements"]

    def fits(ctx, starts, allowed, target, name):
        def completed(row):
            if on_fit is not None:
                on_fit(dict(target=target, proposal=name, fit=row))

        kwargs = {}
        if name is not None and on_selected is not None:
            states = {}
            candidate_states[name] = states
            candidate_contexts[name] = ctx
            kwargs["state_sink"] = states
        return fit_rows(ctx, owners, starts, allowed, on_row=completed, **kwargs)

    for old in targets:
        proposals = [row["hypothesis"] for row in admission["admitted"] if row["target"] == old]
        if not proposals:
            continue
        if historical is None:
            historical, history = complete_history(
                context, active_ids(context), ledger, scan_receipt, collect_history
            )
        starts = dict(
            published=context["problems"]["fitted_c"][1],
            family_omitted=np.asarray(admission["screens"][str(old)]["cavity"]["fitted_c"]["x"]),
        )
        control_rows = fits(historical, starts, set(), old, None)
        controls_by_target[str(old)] = control_rows
        if not fit_rows_complete(control_rows):
            return fallback(
                baseline,
                "incomplete_fit_fallback",
                stage="matched_control",
                target=old,
                records=records,
                guards=admission["guards"],
                failures=control_rows,
            )
        controls = paired(control_rows)
        matched_published = (
            {
                arm: objective(
                    historical["problems"][arm][0], historical, context["problems"][arm][1]
                )
                for arm in ARMS
            }
            if all(controls.values())
            else {}
        )
        bounds = (
            {
                arm: min(
                    controls[arm]["objective"], baseline[arm]["objective"], matched_published[arm]
                )
                for arm in ARMS
            }
            if all(controls.values())
            else {}
        )
        for hypothesis in proposals:
            candidate, info = complete_history(
                historical,
                set(hypothesis["mapping"].values()),
                ledger,
                scan_receipt,
                collect_history,
            )
            candidate = remap(candidate, hypothesis, ledger)
            rows = fits(
                candidate, starts, set(hypothesis["allowed_families"]), old, hypothesis["name"]
            )
            fits_by_proposal[hypothesis["name"]] = rows
            if not fit_rows_complete(rows):
                return fallback(
                    baseline,
                    "incomplete_fit_fallback",
                    stage="admitted_candidate",
                    target=old,
                    records=records,
                    guards=admission["guards"],
                    failures=rows,
                )
            record = score_record(hypothesis, paired(rows), controls, bounds)
            record.update(target=old, history=info, matched_published_objectives=matched_published)
            records.append(record)
            if on_record is not None:
                on_record(deepcopy(record))
    choice = select(baseline, records, admission["guards"])
    if choice["selected"] is not None and on_selected is not None:
        name = choice["selected"]
        row = next(record for record in records if record["name"] == name)
        state = dict(
            candidate_contexts[name],
            problems={
                arm: candidate_states[name][(arm, row["pair"][arm]["start"])] for arm in ARMS
            },
        )
        on_selected(state, deepcopy(row["pair"]))
    return dict(
        choice,
        baseline=deepcopy(baseline),
        records=records,
        guards=admission["guards"],
        targets=targets,
        history=history,
        failures=[],
        propagation_failures=admission["propagation_failures"],
        catalogue_eligibility=admission["catalogue_eligibility"],
        execution_status="complete",
        production_modified=False,
        control_fits=controls_by_target,
        candidate_fits=fits_by_proposal,
    )
