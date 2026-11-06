"""Owned native-GLRT execution through numerical inference and all PNG values.

Execution/admission policies and archive access are supplied through narrow
ports. No historical result, earlier worker or concrete store is an input.
Persisting a completed result and publishing it atomically remain separate.
"""

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from leo.application import localization_v3 as policy


@dataclass(frozen=True)
class ExecutionPorts:
    """Explicit recovery execution and admission; no implicit timeout omissions.

    Stage runners return (completed, value). The gap runner also receives its
    declared time cap. The adapter must enforce cancellation, rather than return
    an unfinished value. Clock and reuse accounting retain the original policy.
    """

    run_stage: Callable
    run_gap_stage: Callable
    discovery_allowed: Callable
    charge_reused: Callable
    clock: Callable
    map_initial_arms: Callable | None = None
    map_predictive_folds: Callable | None = None
    map_family_arms: Callable | None = None
    map_recovery_arms: Callable | None = None
    map_conservative_arms: Callable | None = None
    map_annotation_training: Callable | None = None
    map_grid_batches: Callable | None = None


class IncompleteStage(ValueError):
    def __init__(self, stage, status):
        self.stage, self.status = stage, status
        super().__init__(f"{stage}: incomplete pipeline stage ({status})")


class _Timing:
    def __init__(self, clock, on_stage):
        self.clock, self.on_stage, self.rows = clock, on_stage, []

    def run(self, name, operation, expected=None):
        began = self.clock()
        value = operation()
        ended = self.clock()
        if not all(math.isfinite(v) for v in (began, ended)) or ended < began:
            raise ValueError("Finite monotonic stage clock required")
        status = value.get("status") if isinstance(value, dict) else None
        if expected is not None and status != expected:
            raise IncompleteStage(name, status)
        row = dict(stage=name, seconds=ended - began)
        self.rows.append(row)
        if self.on_stage is not None:
            self.on_stage(dict(row))
        return value


def _json_value(value):
    if isinstance(value, (np.ndarray, np.generic)):
        return value.tolist()
    raise TypeError(type(value).__name__)


def _prepared_values(prepared):
    """Keep the original input value types without writing/reloading a snapshot.

    Graph preparation produces NumPy metadata as well as arrays. The established
    numerical input boundary used JSON for those values and NPZ for the orbit
    bank. Preserve that representation exactly, entirely in memory.
    """
    if prepared["status"] != "inputs_prepared":
        return prepared
    sky = prepared["sky"]
    plain = dict(prepared, sky={k: v for k, v in sky.items() if k != "bank"})
    result = json.loads(json.dumps(plain, default=_json_value, allow_nan=False))
    result["sky"]["bank"] = sky["bank"]
    return result


def infer_prepared(
    prepared, region, catalogue, *, identities, collect_history, execution, on_stage=None
):
    """Run all scientific policies with full original solver budgets.

    Checkpoints are owned in-memory audit/state values, not persisted contracts.
    Evaluation coordinates cannot enter this function. Scientific rejection may
    retain an incumbent; incomplete execution cannot masquerade as completion.
    """
    if prepared["status"] != "inputs_prepared":
        raise IncompleteStage("input", prepared["status"])
    metadata = prepared["sky"]["metadata"]
    if catalogue["cutoff_utc_ns"] != metadata["cutoff_utc_ns"]:
        raise ValueError("Recovery catalogue and native scan cutoffs differ")
    if not identities or len(set(identities)) != len(identities):
        raise ValueError("Explicit unique scan identities required")
    native = prepared["tracks"]
    noise_bytes = (
        json.dumps(prepared["noise"], default=_json_value, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    noise_sha = hashlib.sha256(noise_bytes).hexdigest()
    timing = _Timing(execution.clock, on_stage)
    checkpoints = {}

    def step(name, operation, expected):
        result = timing.run(name, operation, expected)
        checkpoints[name] = result
        return result

    initial = step(
        "initial",
        lambda: policy.fit_initial_position(
            prepared,
            region,
            noise_sha256=noise_sha,
            **({"map_arms": execution.map_initial_arms} if execution.map_initial_arms else {}),
        ),
        "initial_position_fitted",
    )
    conservative = step(
        "conservative",
        lambda: policy.refit_initial_position(
            prepared, initial["initial_fit"], region, noise_sha256=noise_sha,
            **({"map_arms": execution.map_conservative_arms}
               if execution.map_conservative_arms else {}),
        ),
        "conservative_fit_evaluated",
    )
    family = step(
        "family",
        lambda: policy.fit_family_policy(
            prepared, conservative["conservative_fit"], region, noise_sha256=noise_sha,
            **({"map_arms": execution.map_family_arms} if execution.map_family_arms else {}),
        ),
        "family_policy_evaluated",
    )
    signed = step(
        "signed",
        lambda: policy.fit_signed_policy(
            prepared,
            conservative["conservative_fit"],
            family["family_fit"],
            region,
            noise_sha256=noise_sha,
        ),
        "signed_policy_evaluated",
    )
    cavity = step("cavity", lambda: policy.fit_family_cavity(signed), "family_cavity_evaluated")
    inventory = step(
        "inventory",
        lambda: policy.prepare_track_recovery(prepared, signed, cavity, identities=identities),
        "track_recovery_prepared",
    )
    inventory_seconds = timing.rows[-1]["seconds"]
    predictive = step(
        "predictive",
        lambda: policy.recover_predictive_checkpoint(
            inventory,
            run_stage=execution.run_stage,
            discovery_allowed=execution.discovery_allowed,
            clock=execution.clock,
            inventory_seconds=inventory_seconds,
            **(
                {"map_inclusion_arms": execution.map_recovery_arms}
                if execution.map_recovery_arms
                else {}
            ),
            **(
                {"map_annotation_folds": execution.map_predictive_folds}
                if execution.map_predictive_folds
                else {}
            ),
            **(
                {"map_annotation_training": execution.map_annotation_training}
                if execution.map_annotation_training
                else {}
            ),
        ),
        "predictive_recovery_evaluated",
    )
    numerical = step(
        "numerical",
        lambda: policy.recover_numerical_checkpoint(
            inventory,
            predictive,
            run_stage=execution.run_stage,
            discovery_allowed=execution.discovery_allowed,
            clock=execution.clock,
            charge_reused=execution.charge_reused,
            **({"map_inclusion_arms": execution.map_recovery_arms}
               if execution.map_recovery_arms else {}),
        ),
        "numerical_recovery_evaluated",
    )
    gap = step(
        "gap",
        lambda: policy.recover_gap_checkpoint(
            inventory,
            numerical,
            native["observations"],
            run_stage=execution.run_gap_stage,
            clock=execution.clock,
            maximum_seconds=1200,
        ),
        "gap_recovery_evaluated",
    )
    residual = step(
        "residual",
        lambda: policy.prepare_additional_checkpoint(
            inventory, native, metadata, gap, identities=sorted(identities)
        ),
        "additional_recovery_prepared",
    )
    screened = step(
        "residual_screen",
        lambda: policy.screen_additional_recovery(residual, catalogue, region),
        "additional_candidates_screened",
    )
    addition = step(
        "addition",
        lambda: policy.fit_additional_recovery(
            residual, screened, catalogue, native["observations"], clock=execution.clock
        ),
        "additional_position_evaluated",
    )
    incumbent = step(
        "incumbent",
        lambda: policy.prepare_reassociation(
            residual, addition, screened, catalogue, native["observations"]
        ),
        "reassociation_prepared",
    )
    ranking = step(
        "ranking",
        lambda: policy.rank_reassociation_families(incumbent),
        "reassociation_targets_ranked",
    )
    admission = step(
        "admission",
        lambda: policy.screen_reassociation_candidates(incumbent, ranking, catalogue, metadata),
        "reassociation_candidates_screened",
    )
    retained = []
    final = step(
        "final",
        lambda: policy.fit_reassociation(
            incumbent,
            admission,
            catalogue,
            metadata,
            collect_history,
            on_selected=lambda context, pair: retained.append((context, pair)),
        ),
        "reassociation_evaluated",
    )
    if not final["recovery_complete"]:
        raise IncompleteStage("final", final["recovery"]["execution_status"])
    recovery = final["recovery"]
    if recovery["selected"] is None:
        if retained:
            raise ValueError("Rejected repair transferred selected state")
        context, arms, owners = (incumbent[k] for k in ("context", "arms", "owners"))
    else:
        if len(retained) != 1:
            raise ValueError("Exactly one selected final state required")
        context, arms = retained[0]
        owners = {arm: row["proposed_owners"] for arm, row in arms.items()}
    for arm, (_, x) in context["problems"].items():
        if not np.array_equal(x, recovery["final"][arm]["x"]):
            raise ValueError("Selected numerical position differs from final decision")
        if len(owners[arm]) != recovery["final"][arm]["associated"]:
            raise ValueError("Selected native ownership differs from final decision")
    return dict(
        status="numerics_complete",
        checkpoints=checkpoints,
        context=context,
        arms=arms,
        owners=owners,
        native=native,
        stage_timings=timing.rows,
    )


def render_inference(
    inference, *, title, clock, on_stage=None, evaluation_reference=None, grid_seconds=300.0,
    map_grid_batches=None,
):
    """Apply evaluation reference only after completed inference and plot scoring."""
    if inference["status"] != "numerics_complete":
        raise IncompleteStage("presentation", inference["status"])
    from leo.presentation.fast_standard_analysis import render
    from leo.presentation.localization_v3 import prepare_packet
    from leo.presentation.localization_v3_path import recorded_decision_path

    timing = _Timing(clock, on_stage)
    audit, context = inference["checkpoints"], inference["context"]
    region = context["scan"].search_region
    # Current published path/PNG contract has this fixed regional frame.
    if tuple(region.center) != (37.906, -122.545) or region.width_km != 25.0:
        raise ValueError("Current publication renderer requires the declared production region")
    path = recorded_decision_path(
        audit["cavity"]["cavity_fit"],
        region,
        predictive=audit["predictive"]["recovery"],
        numerical=audit["numerical"]["recovery"],
        gap=audit["gap"]["recovery"],
        additional=audit["addition"]["recovery"],
        reassociation=audit["final"]["recovery"],
    )
    packet = timing.run(
        "plot_evidence",
        lambda: prepare_packet(
            context,
            inference["owners"],
            inference["arms"],
            inference["native"]["observations"],
            inference["native"]["tracks"],
            selected_model=path["selected_model"],
            position_path=path,
            grid_seconds=grid_seconds,
            clock=clock,
            map_grid_batches=map_grid_batches,
        ),
    )
    products = timing.run(
        "png_rendering",
        lambda: render(packet, title=title, evaluation_reference=evaluation_reference),
    )
    return dict(
        status="figures_ready",
        packet=packet,
        products=products,
        stage_timings=[*inference["stage_timings"], *timing.rows],
    )


def run_native(
    document,
    archive,
    track_config,
    region,
    *,
    identities,
    execution,
    screen_latitude_deg,
    screen_longitude_deg,
    title,
    on_stage=None,
    evaluation_reference=None,
    grid_seconds=300.0,
):
    """One native preparation/inference/render entry point; does not publish.

    The archive is a read-only port. Final history is collected lazily, only if
    the RF admission policy asks for it. Evaluation coordinates go solely to
    the renderer after every scientific decision and conditional grid score.
    """
    from leo.analysis.localization_v3.elements import ElementParser

    timing = _Timing(execution.clock, on_stage)
    element_parser = ElementParser()
    prepared = timing.run(
        "native_preparation",
        lambda: _prepared_values(
            policy.prepare_native_scan(
                document,
                archive,
                track_config,
                screen_latitude_deg=screen_latitude_deg,
                screen_longitude_deg=screen_longitude_deg,
                element_parser=element_parser,
            )
        ),
    )
    if prepared["status"] != "inputs_prepared":
        return dict(status=prepared["status"], stage_timings=timing.rows, products={})
    cutoff = prepared["sky"]["metadata"]["cutoff_utc_ns"]
    catalogue = timing.run(
        "recovery_catalogue", lambda: policy.prepare_additional_catalogue(
            archive, cutoff, element_parser=element_parser)
    )
    # Retain validated text only across preparation, never in numerical workers.
    element_parser = None
    history = []

    def collect(request):
        from leo.analysis.localization_v3.reassociation_history import select_history

        if not history:
            history.append(policy.prepare_reassociation_history(archive, cutoff))
        return select_history(history[0], request)

    result = infer_prepared(
        prepared,
        region,
        catalogue,
        identities=identities,
        collect_history=collect,
        execution=execution,
        on_stage=on_stage,
    )
    rendered = render_inference(
        result,
        title=title,
        clock=execution.clock,
        on_stage=on_stage,
        evaluation_reference=evaluation_reference,
        grid_seconds=grid_seconds,
        map_grid_batches=execution.map_grid_batches,
    )
    return dict(
        rendered,
        inference=result,
        preparation=prepared,
        catalogue=catalogue,
        stage_timings=[*timing.rows, *rendered["stage_timings"]],
    )
