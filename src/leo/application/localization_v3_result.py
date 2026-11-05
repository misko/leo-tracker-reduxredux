"""Project owned scientific state into immutable evidence and the existing UI port.

No storage implementation or older terminal is imported. Persisting and reading
evidence is delegated to result ports; the current public figure store is a
separate publication port. A saved result can finish publication without a fit.
"""

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import MODEL as POLICY_MODEL
from leo.contracts.localization_v3 import MODEL, validate_evidence, validate_identity


def signed_evidence(context):
    result = {k: v for k, v in context.items() if k not in ("scan", "base")}
    result["original_protected"] = sorted(result["original_protected"])
    p, x = context["base"], context["x"]
    result["base"] = dict(
        calculated=p.calculate(x),
        state=p.state(x),
        residual=p.residual(x),
        conditional_frequency=p.conditional_frequency(x),
        members=p.members,
        labels=p.labels,
        keep=p.keep,
        reference=p.reference,
        events=p.events,
        event_start=p.event_start,
    )
    return result


def audit_evidence(inference):
    """Lossless scientific fields corresponding to the established exact comparator.

    Unlike that external comparator, this stores real arrays, not fingerprints,
    and retains operational timing fields. Live likelihood objects are excluded.
    """
    p = inference["checkpoints"]
    additional = p["residual"]
    selected = additional["residual_context"]
    return dict(
        initial=p["initial"]["initial_fit"],
        recovery=p["conservative"]["conservative_fit"],
        history_policy=p["family"]["family_fit"],
        signed_policy=signed_evidence(p["signed"]["signed_context"]),
        cavity_nominations=p["cavity"]["nominations"],
        cavity_policy=p["cavity"]["cavity_fit"],
        recovery_inventory=p["inventory"]["inventory"],
        predictive_recovery=p["predictive"]["recovery"],
        numerical_recovery=p["numerical"]["recovery"],
        gap_recovery=p["gap"]["recovery"],
        additional_recovery=dict(
            status=additional["status"],
            inventory=additional["residual_inventory"],
            preflight=additional["preflight"],
            selected_owners=p["gap"]["selected_state"]["owners"],
            families=[f.receipt for f in selected["families"]],
            replay_checks=selected["replay_checks"],
            recovery_complete=False,
        ),
        residual_screen=p["residual_screen"],
        additional_position=p["addition"],
        reassociation_handoff={k: v for k, v in p["incumbent"].items() if k != "context"},
        reassociation_trigger=p["ranking"],
        reassociation_screen=p["admission"],
        reassociation_complete=p["final"],
    )


def build_evidence(
    result, *, identity, provenance, title, renderer_revision, evaluation_reference=None
):
    validate_identity(identity)
    if result["status"] != "figures_ready" or result["inference"]["status"] != "numerics_complete":
        raise ValueError("Complete native inference and figures required")
    inference = result["inference"]
    selected = {}
    for arm, (p, x) in inference["context"]["problems"].items():
        selected[arm] = dict(
            x=x, reference=p.reference, calculated=p.calculate(x), state=p.state(x)
        )
    return validate_evidence(
        dict(
            schema_version=1,
            model_version=MODEL,
            status="figures_ready",
            identity=dict(identity),
            provenance=dict(provenance),
            preparation=result["preparation"],
            catalogue=result["catalogue"],
            audit=audit_evidence(inference),
            selected=dict(owners=inference["owners"], arms=inference["arms"], states=selected),
            presentation=result["packet"],
            stage_timings=result["stage_timings"],
            render=dict(
                title=title,
                renderer_revision=renderer_revision,
                evaluation_reference=evaluation_reference,
                reference_usage="evaluation_only",
            ),
        )
    )


def publish_saved(run_id, results, publication):
    """Verify an owned result, then atomically expose all current UI artifacts.

    Only public ports are used. Repeating this operation requires no archive read,
    numerical optimization or rendering. Evaluation coordinates cannot enter
    inference; the persisted rendering reference is attached after publication.
    """
    saved = results.load(run_id)
    evidence = validate_evidence(saved["evidence"])
    receipt = saved["receipt"]
    if (
        evidence["identity"]["run_id"] != run_id
        or receipt["run_id"] != run_id
        or saved["sha256"] != canonical_digest(receipt)
    ):
        raise ValueError("Scientific result publication binding differs")
    packet, render = evidence["presentation"], evidence["render"]
    document = dict(
        schema_version=1,
        **evidence["identity"],
        state="complete",
        model_version=POLICY_MODEL,
        implementation_model=MODEL,
        decision=(
            "ALGO07_reassociation"
            if evidence["audit"]["reassociation_complete"]["recovery"]["selected"] is not None
            else "ALGO06_fallback"
        ),
        selected_model=packet["selected_model"],
        reference_usage="evaluation_only",
        glrt_points=len(packet["observations"]),
        arms=packet["arms"],
        objective_replay=packet["objective_replay"],
        terminal_sha256=saved["sha256"],
        observations_sha256=canonical_digest(packet["observations"]),
        tracks_sha256=canonical_digest(packet["tracks"]),
        figures_model=POLICY_MODEL,
        renderer_revision=render["renderer_revision"],
        figure_frequency_frame="receiver calibration removed; wrapped at GLRT alias period",
        replay_seconds=0.0,
    )
    # A previously saved site must agree before any visible publication changes.
    existing = publication.detail(run_id).get("evaluation_reference")
    reference = render["evaluation_reference"]
    if existing is not None and (
        reference is None
        or any(existing[k] != reference[k] for k in ("latitude_deg", "longitude_deg"))
    ):
        raise ValueError("Saved publication evaluation reference differs from rendered figures")
    value = publication.publish(
        run_id,
        document,
        saved["pngs"],
        position_grid=packet["position_grid"],
        position_path=packet["position_path"],
    )
    if reference is not None:
        publication.set_evaluation_reference(
            run_id, reference["latitude_deg"], reference["longitude_deg"]
        )
    return value
